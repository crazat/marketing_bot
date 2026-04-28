"""실패한 청크를 1개씩 재제출. 429 시 백오프.

Run: python scripts/ai_ad_classify_resubmit.py <job_dir> [--max N] [--delay 30]
"""
import sys, os, json, glob, time, argparse, sqlite3
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

# ai_ad_classify_submit에서 SYSTEM_PROMPT, build_prompt import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_ad_classify_submit import SYSTEM_PROMPT, build_prompt  # noqa: E402
from services.ai_client import ai_generate_batch  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('job_dir')
    p.add_argument('--max', type=int, default=99, help='최대 재제출 청크 수')
    p.add_argument('--delay', type=int, default=30, help='청크 간 대기(초)')
    args = p.parse_args()

    failed = sorted(glob.glob(os.path.join(args.job_dir, 'batch_*_FAILED.json')))
    if not failed:
        print('재제출할 FAILED 청크 없음')
        return
    print(f'재제출 대상: {len(failed)} 청크')

    conn = sqlite3.connect('db/marketing_data.db')
    succeeded = 0

    for fp in failed[:args.max]:
        with open(fp, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        target_ids = meta['target_ids']
        chunk_idx = meta['chunk_idx']

        # viral_targets에서 prompt 데이터 다시 조회
        cur = conn.cursor()
        placeholders = ','.join('?' * len(target_ids))
        rows = cur.execute(f"""
            SELECT id, platform, COALESCE(title,''), COALESCE(content_preview,''), COALESCE(url,'')
            FROM viral_targets WHERE id IN ({placeholders})
        """, target_ids).fetchall()
        # id 순서 유지
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

        # 재시도 (지수 백오프)
        backoff = args.delay
        for attempt in range(4):
            display_name = f'ad_classify_resubmit_chunk{chunk_idx:03d}'
            print(f'\n[chunk {chunk_idx:03d}] 시도 {attempt+1}/4 ({len(requests):,}건)')
            job_name = ai_generate_batch(requests, display_name=display_name)
            if job_name:
                # 성공 → FAILED 파일을 정상 이름으로 재저장
                ok_path = os.path.join(args.job_dir, f'batch_{chunk_idx:03d}.json')
                with open(ok_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'job_name': job_name,
                        'display_name': display_name,
                        'target_ids': target_ids,
                        'count': len(target_ids),
                        'submitted_at': datetime.now().isoformat(),
                        'resubmitted_from': os.path.basename(fp),
                    }, f, ensure_ascii=False, indent=2)
                os.remove(fp)

                # ai_batch_job 마킹
                cur.execute(f'UPDATE viral_targets SET ai_batch_job=? WHERE id IN ({placeholders})',
                            [job_name] + target_ids)
                conn.commit()
                print(f'  ✅ {job_name}')
                succeeded += 1
                # 다음 청크 전 대기 (rate limit 회피)
                if backoff > 0:
                    print(f'  ⏳ 다음 청크까지 {args.delay}초 대기...')
                    time.sleep(args.delay)
                break
            else:
                print(f'  ⏳ {backoff}초 후 재시도...')
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
        else:
            print(f'  ❌ chunk {chunk_idx:03d} 4회 시도 실패 — 다음 청크로')

    conn.close()
    print(f'\n재제출 완료: {succeeded}/{len(failed[:args.max])} 청크 성공')


if __name__ == '__main__':
    main()
