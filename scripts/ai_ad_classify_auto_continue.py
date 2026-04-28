"""자동 데몬: chunk 001 완료 → 검증 → 02~11 순차 제출 → 전체 apply.

설계:
- 모든 단계 logs/ 디렉토리에 텍스트로 기록 (사용자가 아침에 확인)
- status.json 매 단계 업데이트
- 검증 실패 / 타임아웃 / API 에러 시 stop + 사유 기록
- 한 번에 하나의 active batch만 (Free tier 제약)

검증 기준 (chunk 001):
- parse_rate ≥ 90% (JSON 파싱 성공률)
- 단일 라벨 > 90% 면 의심 (편향)
- avg confidence ≥ 0.65

Run: python scripts/ai_ad_classify_auto_continue.py db/batch_jobs/ad_classify_<TS>
"""
import sys, os, json, glob, time, re, sqlite3, subprocess
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'marketing_bot_web', 'backend'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

from services.ai_client import ai_batch_status, ai_batch_results, ai_generate_batch  # noqa
from ai_ad_classify_submit import SYSTEM_PROMPT, build_prompt  # noqa

POLL_INTERVAL = 60  # 60초마다 상태 폴링
MAX_WAIT_PER_CHUNK = 4 * 60 * 60  # 4시간
TOTAL_MAX_HOURS = 16  # 전체 데몬 최대 16시간

VALID_LABELS = ('광고', '광고성_후기톤', '자연_질문', '기타_노이즈')


def setup_logging(job_dir):
    log_path = os.path.join(job_dir, 'auto_continue.log')
    status_path = os.path.join(job_dir, 'auto_status.json')
    return log_path, status_path


def log(msg, log_path):
    line = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(line, flush=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def update_status(status_path, **kwargs):
    cur = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding='utf-8') as f:
                cur = json.load(f)
        except Exception:
            cur = {}
    cur.update(kwargs)
    cur['updated_at'] = datetime.now().isoformat()
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)


def parse_response(text):
    if not text:
        return None
    t = re.sub(r'^```(?:json)?\s*', '', text.strip())
    t = re.sub(r'\s*```$', '', t)
    m = re.search(r'\{[^{}]*\}', t, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        if d.get('label') in VALID_LABELS:
            return {
                'label': d['label'],
                'confidence': float(d.get('confidence', 0.5)),
                'reason': str(d.get('reason', ''))[:80],
            }
    except Exception:
        return None
    return None


def wait_until_done(job_name, log_path, status_path, chunk_label, max_wait=MAX_WAIT_PER_CHUNK):
    """SUCCEEDED 대기. SUCCEEDED/FAILED/EXPIRED/CANCELLED 시 종료."""
    start = time.time()
    last_state = None
    while time.time() - start < max_wait:
        state = ai_batch_status(job_name) or ''
        short = state.split('.')[-1].replace('JOB_STATE_', '')
        if short != last_state:
            log(f'[{chunk_label}] state: {short}', log_path)
            update_status(status_path, current_chunk=chunk_label, current_state=short)
            last_state = short
        if 'SUCCEEDED' in state:
            return True, short
        if any(x in state for x in ('FAILED', 'EXPIRED', 'CANCELLED')):
            return False, short
        time.sleep(POLL_INTERVAL)
    return False, 'TIMEOUT'


def validate_chunk_001(job_dir, log_path):
    """chunk 001 결과 검증. (ok: bool, reason: str, summary: dict)"""
    meta_path = os.path.join(job_dir, 'batch_001.json')
    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    job_name = meta['job_name']
    target_ids = meta['target_ids']

    results = ai_batch_results(job_name)
    if results is None:
        return False, 'ai_batch_results returned None', {}
    if len(results) != len(target_ids):
        return False, f'결과 길이 불일치 (expected {len(target_ids)}, got {len(results)})', {}

    parsed_count = 0
    label_dist = Counter()
    conf_total = 0.0
    parsed_pairs = []  # (tid, parsed) for sample
    for tid, txt in zip(target_ids, results):
        p = parse_response(txt)
        if p:
            parsed_count += 1
            label_dist[p['label']] += 1
            conf_total += p['confidence']
            if len(parsed_pairs) < 200:
                parsed_pairs.append((tid, p))

    parse_rate = parsed_count / len(target_ids)
    avg_conf = conf_total / parsed_count if parsed_count else 0.0
    summary = {
        'total': len(target_ids),
        'parsed': parsed_count,
        'parse_rate': round(parse_rate, 4),
        'avg_confidence': round(avg_conf, 3),
        'label_distribution': dict(label_dist),
    }
    log(f'  검증 — total={summary["total"]}, parsed={summary["parsed"]} ({parse_rate*100:.1f}%), avg_conf={avg_conf:.2f}', log_path)
    log(f'  라벨 분포: {dict(label_dist)}', log_path)

    # 샘플 30건 (각 라벨 비례) 저장 — 사용자 검토용
    sample_path = os.path.join(job_dir, 'validation_sample.txt')
    conn = sqlite3.connect('db/marketing_data.db')
    cur = conn.cursor()
    by_label = {l: [] for l in VALID_LABELS}
    for tid, p in parsed_pairs:
        if len(by_label[p['label']]) < 8:
            by_label[p['label']].append((tid, p))

    with open(sample_path, 'w', encoding='utf-8') as f:
        f.write('=== chunk 001 검증 샘플 (사용자 아침 확인용) ===\n\n')
        f.write(f'총 {summary["total"]:,}건 / 파싱 {parsed_count:,}건 ({parse_rate*100:.1f}%)\n')
        f.write(f'평균 신뢰도: {avg_conf:.2f}\n')
        f.write(f'라벨 분포: {dict(label_dist)}\n\n')
        for label in VALID_LABELS:
            f.write(f'\n--- {label} (각 라벨 최대 8건) ---\n')
            for tid, p in by_label[label]:
                row = cur.execute("SELECT title, content_preview FROM viral_targets WHERE id=?", (tid,)).fetchone()
                if row:
                    title = (row[0] or '')[:80]
                    prev = (row[1] or '').replace('\n',' ')[:120]
                    f.write(f'  conf={p["confidence"]:.2f}  reason={p["reason"]}\n')
                    f.write(f'    title: {title}\n')
                    f.write(f'    prev : {prev}\n\n')
    conn.close()

    # 검증 기준
    if parse_rate < 0.9:
        return False, f'parse_rate {parse_rate*100:.1f}% < 90%', summary
    if avg_conf < 0.65:
        return False, f'avg_confidence {avg_conf:.2f} < 0.65', summary
    max_label_pct = max(label_dist.values()) / parsed_count if parsed_count else 0
    if max_label_pct > 0.9:
        return False, f'단일 라벨 편향 {max_label_pct*100:.1f}% > 90%', summary

    return True, 'OK', summary


def submit_chunk(job_dir, chunk_idx, log_path, status_path):
    """FAILED 청크를 재제출. 성공 시 메타 저장."""
    failed_path = os.path.join(job_dir, f'batch_{chunk_idx:03d}_FAILED.json')
    if not os.path.exists(failed_path):
        return None
    with open(failed_path, encoding='utf-8') as f:
        meta = json.load(f)
    target_ids = meta['target_ids']

    conn = sqlite3.connect('db/marketing_data.db')
    cur = conn.cursor()
    placeholders = ','.join('?' * len(target_ids))
    rows = cur.execute(f"""
        SELECT id, platform, COALESCE(title,''), COALESCE(content_preview,''), COALESCE(url,'')
        FROM viral_targets WHERE id IN ({placeholders})
    """, target_ids).fetchall()
    id2row = {r[0]: r for r in rows}
    ordered = [id2row[tid] for tid in target_ids if tid in id2row]

    requests = []
    for tid, plat, title, prev, url in ordered:
        requests.append({
            'prompt': build_prompt(plat, title, prev, url),
            'system_prompt': SYSTEM_PROMPT,
            'temperature': 0.2,
            'max_tokens': 128,
        })

    # 재시도 (지수 백오프) — chunk가 여전히 RUNNING 중이면 잠시 후 재시도
    backoff = 30
    for attempt in range(8):
        log(f'[chunk {chunk_idx:03d}] 제출 시도 {attempt+1}/8', log_path)
        job_name = ai_generate_batch(requests, display_name=f'ad_classify_auto_chunk{chunk_idx:03d}')
        if job_name:
            ok_path = os.path.join(job_dir, f'batch_{chunk_idx:03d}.json')
            with open(ok_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'job_name': job_name,
                    'display_name': f'ad_classify_auto_chunk{chunk_idx:03d}',
                    'target_ids': target_ids,
                    'count': len(target_ids),
                    'submitted_at': datetime.now().isoformat(),
                    'auto_resubmitted': True,
                }, f, ensure_ascii=False, indent=2)
            os.remove(failed_path)
            cur.execute(f'UPDATE viral_targets SET ai_batch_job=? WHERE id IN ({placeholders})',
                        [job_name] + target_ids)
            conn.commit()
            conn.close()
            log(f'[chunk {chunk_idx:03d}] ✅ 제출 성공: {job_name}', log_path)
            return job_name
        log(f'[chunk {chunk_idx:03d}] 실패, {backoff}초 대기...', log_path)
        time.sleep(backoff)
        backoff = min(backoff * 2, 600)
    conn.close()
    log(f'[chunk {chunk_idx:03d}] ❌ 8회 시도 실패, 포기', log_path)
    return None


def send_telegram(msg):
    """Telegram 알림 (env에 있으면)."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    try:
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': msg[:4000],
        }).encode()
        urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data=data, timeout=10)
    except Exception as e:
        print(f'[telegram] 실패: {e}')


def main():
    if len(sys.argv) < 2:
        print('Usage: python ai_ad_classify_auto_continue.py <job_dir>')
        sys.exit(1)
    job_dir = sys.argv[1]
    log_path, status_path = setup_logging(job_dir)
    started_at = time.time()

    log(f'=== 자동 데몬 시작 (job_dir={job_dir}) ===', log_path)
    update_status(status_path, started_at=datetime.now().isoformat(), step='start', stopped=False)

    # ── Phase 1: chunk 001 완료 대기 + 검증 ──
    with open(os.path.join(job_dir, 'batch_001.json'), encoding='utf-8') as f:
        c1_meta = json.load(f)
    log(f'Phase 1: chunk 001 대기 (job={c1_meta["job_name"]})', log_path)
    update_status(status_path, step='waiting_chunk_001')

    ok, state = wait_until_done(c1_meta['job_name'], log_path, status_path, 'chunk 001')
    if not ok:
        log(f'❌ chunk 001 실패/타임아웃 — 상태: {state}. 데몬 중단.', log_path)
        update_status(status_path, step='failed', failure_reason=f'chunk 001 not SUCCEEDED: {state}', stopped=True)
        send_telegram(f'[AI 분류 자동] ❌ chunk 001 {state}, 데몬 중단')
        return

    log('✅ chunk 001 SUCCEEDED. 검증 시작.', log_path)
    update_status(status_path, step='validating_chunk_001')
    valid_ok, valid_reason, summary = validate_chunk_001(job_dir, log_path)
    update_status(status_path, validation=summary, validation_passed=valid_ok, validation_reason=valid_reason)

    if not valid_ok:
        log(f'⚠️ 검증 실패: {valid_reason}. 02~11 청크 제출 안 함. 데몬 중단.', log_path)
        update_status(status_path, step='validation_failed', stopped=True)
        send_telegram(f'[AI 분류 자동] ⚠️ chunk 001 검증 실패: {valid_reason}\n분포: {summary.get("label_distribution", {})}')
        return

    log(f'✅ 검증 통과 ({valid_reason}). 02~11 청크 순차 제출 시작.', log_path)

    # ── Phase 2: 02~11 청크 순차 제출 + 대기 ──
    failed_chunks = sorted(glob.glob(os.path.join(job_dir, 'batch_*_FAILED.json')))
    chunk_indices = sorted([int(re.search(r'batch_(\d+)_FAILED', f).group(1)) for f in failed_chunks])
    log(f'Phase 2: 제출 대상 청크 {chunk_indices}', log_path)

    for cidx in chunk_indices:
        # 전체 시간 한도 체크
        if time.time() - started_at > TOTAL_MAX_HOURS * 3600:
            log(f'⏰ 전체 한도 {TOTAL_MAX_HOURS}h 초과. 중단.', log_path)
            update_status(status_path, step='global_timeout', stopped=True)
            send_telegram(f'[AI 분류 자동] ⏰ {TOTAL_MAX_HOURS}h 한도 초과, chunk {cidx-1:03d}까지 처리 후 중단')
            return

        update_status(status_path, step=f'submitting_chunk_{cidx:03d}')
        job_name = submit_chunk(job_dir, cidx, log_path, status_path)
        if not job_name:
            log(f'❌ chunk {cidx:03d} 제출 영구 실패. 다음 청크 시도.', log_path)
            continue

        # 이 청크 완료 대기 (다음 청크 제출하려면 active batch 비워야 함)
        update_status(status_path, step=f'waiting_chunk_{cidx:03d}', current_job=job_name)
        ok, state = wait_until_done(job_name, log_path, status_path, f'chunk {cidx:03d}')
        if not ok:
            log(f'❌ chunk {cidx:03d} {state} — 다음 청크로 진행', log_path)
            continue
        log(f'✅ chunk {cidx:03d} SUCCEEDED', log_path)

    # ── Phase 3: apply ──
    log('Phase 3: apply 스크립트 실행', log_path)
    update_status(status_path, step='applying')
    try:
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', 'scripts/ai_ad_classify_apply.py', job_dir],
            capture_output=True, text=True, encoding='utf-8', timeout=600
        )
        apply_log_path = os.path.join(job_dir, 'apply_output.txt')
        with open(apply_log_path, 'w', encoding='utf-8') as f:
            f.write('STDOUT:\n')
            f.write(result.stdout or '')
            f.write('\n\nSTDERR:\n')
            f.write(result.stderr or '')
        log(f'apply 결과 → {apply_log_path}', log_path)
        update_status(status_path, step='completed', stopped=True)
        send_telegram(f'[AI 분류 자동] ✅ 전체 완료. 로그: {apply_log_path}')
    except Exception as e:
        log(f'❌ apply 실패: {e}', log_path)
        update_status(status_path, step='apply_failed', apply_error=str(e), stopped=True)
        send_telegram(f'[AI 분류 자동] ❌ apply 실패: {e}')

    log('=== 데몬 종료 ===', log_path)


if __name__ == '__main__':
    main()
