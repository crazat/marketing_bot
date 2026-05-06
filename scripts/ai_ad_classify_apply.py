"""배치 분류 결과 회수 + viral_targets에 라벨 UPDATE.

Logic:
  - confidence >= 0.7 + label in ('광고', '광고성_후기톤', '기타_노이즈') -> comment_status='filtered_out_ai'
  - [Q4] post_region == '타지역' -> 무조건 filtered_out_ai (다른 도시 글은 우리에게 무가치)
  - [Q5] specialty_match == 'low' AND label != '자연_질문' -> filtered_out_ai (한의원 무관)
  - confidence < 0.7 -> 사람 검토 (comment_status는 pending 유지, 라벨만 기록)
  - label = '자연_질문' AND post_region != '타지역' AND specialty_match != 'low' -> pending 유지

Run: python scripts/ai_ad_classify_apply.py db/batch_jobs/ad_classify_<TS>
"""
import sys, os, json, glob, re, sqlite3, argparse
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

from services.ai_client import ai_batch_status, ai_batch_results  # noqa: E402

VALID_LABELS = ('광고', '광고성_후기톤', '자연_질문', '기타_노이즈')
FILTER_LABELS = ('광고', '광고성_후기톤', '기타_노이즈')
VALID_REGIONS = ('청주', '세종', '충주', '증평', '타지역', '불명')
VALID_SPECIALTY = ('high', 'medium', 'low')
CONFIDENCE_THRESHOLD = 0.7


def parse_response(text: str) -> dict | None:
    """Gemini 응답 텍스트에서 JSON 객체 추출."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*', '', t)
    t = re.sub(r'\s*```$', '', t)
    m = re.search(r'\{[^{}]*\}', t, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        if 'label' in d and d.get('label') in VALID_LABELS:
            region = d.get('post_region') if d.get('post_region') in VALID_REGIONS else '불명'
            specialty = d.get('specialty_match') if d.get('specialty_match') in VALID_SPECIALTY else None
            return {
                'label': d['label'],
                'post_region': region,
                'specialty_match': specialty,
                'confidence': float(d.get('confidence', 0.5)),
                'reason': str(d.get('reason', ''))[:80],
            }
    except Exception:
        return None
    return None


def _execute_scoped_update(
    cur: sqlite3.Cursor,
    set_sql: str,
    params: list,
    target_id: str,
    source_scan_run_id: int | None,
) -> int:
    if source_scan_run_id is None:
        cur.execute(f"UPDATE viral_targets SET {set_sql} WHERE id=?", params + [target_id])
    else:
        cur.execute(
            f"UPDATE viral_targets SET {set_sql} WHERE id=? AND source_scan_run_id=?",
            params + [target_id, int(source_scan_run_id)],
        )
    return cur.rowcount


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job_dir', help='db/batch_jobs/ad_classify_<TS>')
    parser.add_argument(
        '--source-scan-run-id',
        type=int,
        default=None,
        help='이 run의 target만 업데이트. 미지정 시 batch JSON metadata 값을 사용',
    )
    args = parser.parse_args()
    job_dir = args.job_dir

    files = sorted(glob.glob(os.path.join(job_dir, 'batch_*.json')))
    files = [f for f in files if 'FAILED' not in f]
    if not files:
        print(f'배치 파일 없음: {job_dir}')
        sys.exit(1)

    # 모든 배치 SUCCEEDED인지 확인
    print('--- 상태 확인 ---')
    not_ready = []
    for fp in files:
        with open(fp, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        state = ai_batch_status(meta['job_name']) or ''
        if 'SUCCEEDED' not in state:
            short = state.split('.')[-1]
            not_ready.append((os.path.basename(fp), short))
    if not_ready:
        print('❌ 아직 완료 안 된 배치 있음:')
        for fname, st in not_ready:
            print(f'  {fname}: {st}')
        sys.exit(2)
    print('✅ 모두 SUCCEEDED')

    # 결과 회수 + UPDATE
    db_path = os.environ.get('MARKETING_BOT_DB_PATH', 'db/marketing_data.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    label_count = Counter()
    parse_fail = 0
    updated = 0
    filtered = 0
    review_q = 0
    retry_marked = 0
    skipped_scope = 0

    now = datetime.now().isoformat()

    for fp in files:
        with open(fp, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        job_name = meta['job_name']
        target_ids = meta['target_ids']
        batch_source_scan_run_id = (
            args.source_scan_run_id
            if args.source_scan_run_id is not None
            else meta.get('source_scan_run_id')
        )
        results = ai_batch_results(job_name)
        if results is None or len(results) != len(target_ids):
            print(f'⚠️ {os.path.basename(fp)}: 결과 길이 불일치 (expected {len(target_ids)}, got {len(results) if results else 0})')
            continue

        for tid, txt in zip(target_ids, results):
            parsed = parse_response(txt)
            if parsed is None:
                parse_fail += 1
                rowcount = _execute_scoped_update(
                    cur,
                    "ai_ad_reason=?, ai_classified_at=?, comment_status=?",
                    ['parse_failed', now, 'needs_ai_retry'],
                    tid,
                    batch_source_scan_run_id,
                )
                if rowcount:
                    retry_marked += rowcount
                    updated += rowcount
                else:
                    skipped_scope += 1
                continue

            new_status = None

            # [Q4] 타지역 글은 무조건 filter (자연_질문이라도 우리에게 응답 가치 없음)
            # [Q5] specialty_match=low + 자연_질문 아닌 경우도 filter (한의원 무관)
            high_conf = parsed['confidence'] >= CONFIDENCE_THRESHOLD
            if high_conf and parsed['post_region'] == '타지역':
                new_status = 'filtered_out_ai'
            elif high_conf and parsed['label'] in FILTER_LABELS:
                new_status = 'filtered_out_ai'
            elif (
                high_conf
                and parsed['specialty_match'] == 'low'
                and parsed['label'] != '자연_질문'
            ):
                new_status = 'filtered_out_ai'

            if new_status:
                rowcount = _execute_scoped_update(
                    cur,
                    """
                    ai_ad_label=?, ai_ad_confidence=?, ai_ad_reason=?, ai_classified_at=?,
                    post_region=?, specialty_match=?, comment_status=?
                    """,
                    [
                    parsed['label'], parsed['confidence'], parsed['reason'], now,
                    parsed['post_region'], parsed['specialty_match'], new_status,
                    ],
                    tid,
                    batch_source_scan_run_id,
                )
            else:
                rowcount = _execute_scoped_update(
                    cur,
                    """
                    ai_ad_label=?, ai_ad_confidence=?, ai_ad_reason=?, ai_classified_at=?,
                    post_region=?, specialty_match=?
                    """,
                    [
                    parsed['label'], parsed['confidence'], parsed['reason'], now,
                    parsed['post_region'], parsed['specialty_match'],
                    ],
                    tid,
                    batch_source_scan_run_id,
                )

            if rowcount:
                updated += rowcount
                label_count[parsed['label']] += rowcount
                if new_status == 'filtered_out_ai':
                    filtered += rowcount
                elif parsed['confidence'] < CONFIDENCE_THRESHOLD:
                    review_q += rowcount
            else:
                skipped_scope += 1

        conn.commit()
        print(f'  ✅ {os.path.basename(fp)}: {len(target_ids):,}건 처리')

    conn.close()

    print('\n' + '=' * 70)
    print('  AI 분류 결과 적용 완료')
    print('=' * 70)
    print(f'\n  총 UPDATE: {updated:,}건')
    print(f'  파싱 실패: {parse_fail:,}건')
    print(f'  → 재시도 큐 표시: {retry_marked:,}건')
    if skipped_scope:
        print(f'  → source_scan_run_id 범위 불일치/미존재로 건너뜀: {skipped_scope:,}건')
    print(f'  → filtered_out_ai 적용: {filtered:,}건')
    print(f'  → 사람 검토 큐 (낮은 신뢰도): {review_q:,}건')
    print('\n  라벨 분포:')
    for label, n in label_count.most_common():
        print(f'    {label:<15}  {n:>6,}건')

    # 최종 viral_targets 분포
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    print('\n  최종 comment_status 분포:')
    for r in cur.execute("SELECT comment_status, COUNT(*) FROM viral_targets GROUP BY comment_status ORDER BY 2 DESC").fetchall():
        print(f'    {(r[0] or "NULL"):<20}  {r[1]:>6,}건')
    conn.close()

    print('\n✅ 완료. 복원 필요 시:')
    print("   UPDATE viral_targets SET comment_status='pending' WHERE comment_status='filtered_out_ai';")


if __name__ == '__main__':
    main()
