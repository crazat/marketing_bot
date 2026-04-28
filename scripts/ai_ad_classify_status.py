"""배치 분류 작업 상태 조회.

Run: python scripts/ai_ad_classify_status.py db/batch_jobs/ad_classify_<TS>
"""
import sys, os, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

from services.ai_client import ai_batch_status  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/ai_ad_classify_status.py <batch_jobs_dir>')
        sys.exit(1)

    job_dir = sys.argv[1]
    files = sorted(glob.glob(os.path.join(job_dir, 'batch_*.json')))
    if not files:
        print(f'배치 파일 없음: {job_dir}')
        sys.exit(1)

    print(f'{job_dir}')
    print('=' * 70)

    counts = {}
    total_items = 0
    for fp in files:
        with open(fp, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        if 'FAILED' in fp:
            print(f'  {os.path.basename(fp):<28}  ❌ submit FAILED')
            continue
        job_name = meta['job_name']
        n = meta['count']
        total_items += n
        state = ai_batch_status(job_name) or '(unknown)'
        # state는 "JobState.JOB_STATE_SUCCEEDED" 등으로 옴 — 마지막 토큰만
        short = state.split('.')[-1].replace('JOB_STATE_', '')
        counts[short] = counts.get(short, 0) + 1
        emoji = {'SUCCEEDED': '✅', 'FAILED': '❌', 'RUNNING': '🔄', 'PENDING': '⏳',
                 'EXPIRED': '⏰', 'CANCELLED': '🚫'}.get(short, '❓')
        print(f'  {os.path.basename(fp):<28}  {emoji} {short:<14}  ({n:,}건)  {job_name[-20:]}')

    print('\n--- 요약 ---')
    print(f'  총 청크: {len(files)}  총 요청: {total_items:,}건')
    for state, n in sorted(counts.items()):
        print(f'  {state:<14}  {n} 청크')
    if counts.get('SUCCEEDED', 0) == len(files):
        print('\n✅ 모두 완료. 다음 단계:')
        print(f'  python scripts/ai_ad_classify_apply.py {job_dir}')


if __name__ == '__main__':
    main()
