"""viral_targets pending 글을 광고/자연 4-class로 배치 분류.

Output: db/batch_jobs/ad_classify_<TS>/batch_NNN.json
Each: {"job_name": "...", "target_ids": [<viral_target.id ordered>], "submitted_at": "..."}

Run: python scripts/ai_ad_classify_submit.py [--limit N] [--chunk 5000] [--dry-run]
"""
import sys, os, json, sqlite3, argparse
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

from services.ai_client import ai_generate_batch  # noqa: E402

SYSTEM_PROMPT = """당신은 한국 한의원 마케팅 데이터에서 "사용자 자연 글" vs "광고/마케팅 글"을 정확히 분류하는 전문가입니다.

목적: 청주 규림한의원이 댓글로 응답할 가치 있는 진짜 잠재 고객 질문/후기인지 판단.

응답에는 4개 필드를 모두 포함해야 합니다: label, post_region, specialty_match, confidence, reason.

[필드 1] label (분류 라벨, 반드시 4개 중 하나):
1. "광고" — 한의원/병원/제품/서비스 홍보 명백. 후기 형식이라도 마케팅 의도 분명. 가격/예약/위치 정보 노출.
2. "광고성_후기톤" — 자연인 후기를 가장하나 정형화된 마케팅 톤. "내돈내산", "꼼꼼하게", "친절한 상담", 매끄러운 문체, 특정 한의원/병원/제품 이름 등장.
3. "자연_질문" — 실제 사용자가 증상/병원 추천/치료 정보를 구하는 진정한 질문. 망설임/불안/구체적 상황 묘사 있음.
4. "기타_노이즈" — 우리(한의원·한방) 분야와 무관 (미용실/변호사/댄스/베이비카페/PT/부동산/학원 등).

[필드 2] post_region (게시자 거주지/관심지역):
- "청주" — 청주/오창/오송/흥덕구/상당구/서원구/청원구
- "세종" — 세종시
- "충주" — 충주시
- "증평" — 증평군
- "타지역" — 천안/수원/대전/부천/서울/부산/광주/대구/인천 등 충북 외 도시 광고나 거주지가 명확히 청주권 외
- "불명" — 지역 정보 없음. 청주 키워드만 검색되어 등장하나 본문에 거주지 단서 없음

판단 기준:
- 본문에 "충북 청주", "청주 살아요", "청주 사는데" 등 거주지 표현 → 해당 지역
- "청주에서 살다가 천안 이사" / "천안 → 청주 이사예정" 같은 이주 표현은 현재 거주지 기준
- 광고는 업체 위치 기준
- 순수 검색 키워드만 매칭(본문에는 다른 지역) → "타지역"

[필드 3] specialty_match (한의원 진료 영역 적합도):

⭐ 규림한의원 핵심 미용 주력 (반드시 high) — 다이어트/한약, 안면비대칭/체형교정/골반교정, 한방 피부치료/여드름, 추나요법, 거북목/일자목, 교통사고/한방 자동차보험, 디스크/허리·목 통증.

- "high" — 위 핵심 미용 주력 + 한의원 직접 진료 영역 (탈모 한방치료, 소화기, 두통/어지럼, 비염 한방).
- "medium" — 한방 관련성 있지만 부수적 (수험생 집중력, 갱년기, 자율신경, 소아 한방, 면역/보약).
- "low" — 한의원 무관 (양방 전문, 미용실, 에스테틱, 보험합의금, 부동산, 일반 잡담).

⚠️ 중요한 경계 케이스 (이전 버전 hallucination 방지):
1. **산후조리원 후기 글** (조리원 시설/서비스/식단 메인 + 한약/한방 한 줄 언급)
   → specialty_match="medium" (NOT high). 산후 보약 자체가 메인 주제일 때만 high.
   예: "프라우 산후조리원 6박7일 후기" + 본문에 "보약도 먹었어요" → medium.
   예: "산후 보약 어디서 받으셨어요? 추천부탁드려요" → high.

2. **에스테틱/피부관리실 후기** (양방 미용 시술 — 리프팅/볼륨/필러/레이저)
   → specialty_match="low". 한방 피부치료(여드름/아토피)와 구분.

3. **양방 정형외과/피부과/피부미용실** 추천글 → low. 단 한의원 비교 질문이면 medium.

4. **이사·매물·인테리어** 글 + 한의원 한 줄 등장 → low (label="기타_노이즈").

5. 본문이 짧거나 단편적이면 reason은 "본문 부족"이라 솔직히 명시. 추측 금지.

[신뢰도 confidence] 0.0~1.0:
- 0.9+ : 매우 명확
- 0.7~0.9: 명확
- 0.5~0.7: 애매 (사람 검토 권장)
- 0.5 미만: 판단 불가

광고 시그널:
- "내돈내산", "정말 추천", "후기 남깁니다" + 매끄러운 문체
- 가격대, 영업시간, 위치 본문 명시
- 같은 패턴 칭찬 형용사("꼼꼼하게", "친절하게", "전문적인")
- 특정 한의원/병원 이름이 자연스럽게 등장

자연 질문 시그널:
- 구체적 증상 (시기/정도/동반증상)
- 망설임 표현 ("ㅠㅠ", "...", "고민", "어떻게 해야")
- 비교/대안 요청 ("A vs B", "이게 나을까요")
- 맘카페 특수 시그널: "우리아이", "진짜추천부탁드려요", "맘님들", "ㅜㅜ", "혹시 다녀보신분" → 자연_질문 신호 강함

예시:
[입력] platform=blog title="청주다이어트한약추천내돈내산으로 해보신분?" preview="안녕하세요 청주에서 살고 있는 30대 직장인입니다 출산하고 계속..."
[출력] {"label":"광고성_후기톤","post_region":"청주","specialty_match":"high","confidence":0.9,"reason":"내돈내산 정형톤"}

[입력] platform=kin title="청주 다이어트 한약효과 정말 있을까요?" preview="안녕하세요 출산후 6개월차인데 살이 안빠져서 고민이에요. 한약 처방받아본 분 계신가요?"
[출력] {"label":"자연_질문","post_region":"불명","specialty_match":"high","confidence":0.85,"reason":"구체적 상황+망설임"}

[입력] platform=cafe title="천안한의원다이어트 후기" preview="천안에 새로 생긴 한의원 다녀왔어요..."
[출력] {"label":"기타_노이즈","post_region":"타지역","specialty_match":"high","confidence":0.95,"reason":"다른 지역"}

[입력] platform=cafe title="청주 맘님들 우리아이 비염 한방치료 다녀보신분ㅜㅜ" preview="6살 아이 비염이 너무 심해서요. 양방은 효과가 잠깐이라 한방 치료를 알아보고있는데 진짜추천부탁드려요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"high","confidence":0.95,"reason":"맘카페 자연 톤"}

[입력] platform=blog title="가경동피부관리 이브온에스테틱 청주본점 리프팅 맞춤케어 후기" preview="충북 청주시 흥덕구 서현중로 16... 영업시간 10:00-20:00..."
[출력] {"label":"광고","post_region":"청주","specialty_match":"low","confidence":0.95,"reason":"에스테틱 광고"}

[입력] platform=kin title="청주 복대동 머리 잘하는 곳 추천해주세요" preview="펌, 염색 잘하는 미용실..."
[출력] {"label":"기타_노이즈","post_region":"청주","specialty_match":"low","confidence":0.95,"reason":"미용실"}

[입력] platform=kin title="오늘허리를다쳤는데요" preview="ㅠ 이것저것 찾아보는데 점점 두렵기만 하네요. 청주에서 잘하는 한의원 좀 소개시켜주세요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"high","confidence":0.9,"reason":"증상+추천요청"}

[입력] platform=instagram title="EV6 고속도로 후미추돌 피해 동일차종으로 배차해 드렸습니다" preview="사고대차/일상배상/사고수리 카카오톡 연락주세요"
[출력] {"label":"광고","post_region":"불명","specialty_match":"low","confidence":0.98,"reason":"사고대차업체"}

[입력] platform=kin title="청주에서 허리협착증 수술 잘하는 곳 있을까요?" preview="대학병원으로 가야할지 아님 척추 전문 병원으로 가야할지 고민이에요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"medium","confidence":0.9,"reason":"양방 비교"}

[입력] platform=cafe title="청주에서 살다가 천안으로 이사가는데 한의원 추천" preview="다음달에 천안으로 이사예정이라 그쪽 한의원 추천 부탁드려요"
[출력] {"label":"기타_노이즈","post_region":"타지역","specialty_match":"high","confidence":0.9,"reason":"이사 후 타지역"}

[입력] platform=blog title="청주 미즈맘 산후조리원 6박7일 후기 (몽골인 산모 이용 후기)" preview="조리원 시설, 식단, 케어 후기 위주. 마지막에 회복 한약 먹었다는 한 줄."
[출력] {"label":"광고성_후기톤","post_region":"청주","specialty_match":"medium","confidence":0.85,"reason":"조리원후기+한약1줄"}

[입력] platform=cafe title="청주 산후 보약 어디서 받으셨어요 추천부탁드려요" preview="첫째 출산 후 기력 회복 안 돼서요. 한의원에서 산후보약 처방 받는다는데 어디가 좋을까요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"high","confidence":0.95,"reason":"산후보약 한의원 추천"}

[입력] platform=blog title="청주 거북목 일자목 추나 받고 후기" preview="컴퓨터 작업 많아서 거북목인데 한의원 추나 받고 효과 봤어요"
[출력] {"label":"광고성_후기톤","post_region":"청주","specialty_match":"high","confidence":0.9,"reason":"추나후기 한의원"}

[입력] platform=kin title="청주 안면비대칭 교정 한의원 추천" preview="턱 비대칭이 심해서 추나로 교정한다는데 청주에 잘하는 곳 있나요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"high","confidence":0.95,"reason":"안면비대칭 추나 추천"}

[입력] platform=cafe title="청주 가경동 피부과 여드름 치료" preview="여드름이 심해서 피부과 치료 받았는데 별로예요. 다른 방법 있을까요"
[출력] {"label":"자연_질문","post_region":"청주","specialty_match":"medium","confidence":0.85,"reason":"양방 피부과 비교 가능성"}

응답 형식 (반드시 마크다운 fence 없이 단일 JSON 객체만):
{"label":"<라벨>","post_region":"<지역>","specialty_match":"<high|medium|low>","confidence":<숫자>,"reason":"<10자 이내 사유>"}
"""


def build_prompt(platform: str, title: str, preview: str, url: str) -> str:
    """단일 분류 요청 prompt — content 우선 + 1500자 (hallucination 감소)."""
    title_s = (title or '').replace('\n', ' ')[:300]
    prev_s = (preview or '').replace('\n', ' ').replace('\r', ' ')[:1500]
    return (
        f"plat={platform}\n"
        f"title={title_s}\n"
        f"body={prev_s}\n"
        f"JSON:"
    )


def fetch_pending(limit: int | None = None, source_scan_run_id: int | None = None):
    conn = sqlite3.connect(os.environ.get('MARKETING_BOT_DB_PATH', 'db/marketing_data.db'))
    c = conn.cursor()
    # [2026-04-28] content(enrich된 본문) 있으면 우선, 없으면 content_preview
    # AI hallucination 감소를 위해 본문을 길게 제공 (1500자)
    sql = """
        SELECT id, platform, COALESCE(title,''),
               COALESCE(NULLIF(content,''), content_preview, '') AS body,
               COALESCE(url,'')
        FROM viral_targets
        WHERE comment_status='pending' AND ai_ad_label IS NULL
    """
    params = []
    if source_scan_run_id is not None:
        sql += " AND source_scan_run_id = ?"
        params.append(int(source_scan_run_id))
    sql += " ORDER BY platform, id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = c.execute(sql, params).fetchall()
    conn.close()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=None, help='최대 제출 건수 (기본: 전체)')
    p.add_argument('--chunk', type=int, default=5000, help='배치당 최대 요청 수')
    p.add_argument('--dry-run', action='store_true', help='제출 안 하고 카운트만')
    p.add_argument('--source-scan-run-id', type=int, default=None,
                   help='특정 source_scan_run_id의 viral_targets만 제출')
    args = p.parse_args()

    rows = fetch_pending(args.limit, args.source_scan_run_id)
    total = len(rows)
    print(f'대상: {total:,}건')
    if args.source_scan_run_id is not None:
        print(f'source_scan_run_id: {args.source_scan_run_id}')
    if total == 0:
        print('처리할 pending 없음.')
        return

    # 시스템 프롬프트 길이 확인
    print(f'system_prompt 길이: {len(SYSTEM_PROMPT):,} 자')

    if args.dry_run:
        print('--- DRY RUN ---')
        sample = rows[0]
        print('샘플 prompt:')
        print(build_prompt(sample[1], sample[2], sample[3], sample[4]))
        print('\n--- 끝 (실제 제출 안 함) ---')
        return

    # 디렉토리 생성
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join('db', 'batch_jobs', f'ad_classify_{ts}')
    os.makedirs(out_dir, exist_ok=True)
    print(f'출력 디렉토리: {out_dir}')

    # 청크 단위 제출
    chunk_size = args.chunk
    chunks_total = (total + chunk_size - 1) // chunk_size
    submitted = []

    for cidx in range(chunks_total):
        start = cidx * chunk_size
        end = min(start + chunk_size, total)
        chunk = rows[start:end]

        requests = []
        for tid, plat, title, preview, url in chunk:
            requests.append({
                'prompt': build_prompt(plat, title, preview, url),
                'system_prompt': SYSTEM_PROMPT,
                'temperature': 0.2,
                'max_tokens': 128,
            })

        display_name = f'ad_classify_{ts}_chunk{cidx+1:03d}'
        print(f'\n[{cidx+1}/{chunks_total}] 제출 중 ({len(requests):,}건)... display_name={display_name}')

        job_name = ai_generate_batch(requests, display_name=display_name)
        if not job_name:
            print(f'  ❌ 제출 실패 (chunk {cidx+1})')
            # 부분 성공 기록
            with open(os.path.join(out_dir, f'batch_{cidx+1:03d}_FAILED.json'), 'w', encoding='utf-8') as f:
                json.dump({
                    'chunk_idx': cidx + 1,
                    'error': 'submit failed',
                    'target_ids': [r[0] for r in chunk],
                }, f, ensure_ascii=False, indent=2)
            continue

        # 매핑 저장
        target_ids = [r[0] for r in chunk]
        path = os.path.join(out_dir, f'batch_{cidx+1:03d}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'job_name': job_name,
                'display_name': display_name,
                'target_ids': target_ids,
                'source_scan_run_id': args.source_scan_run_id,
                'count': len(target_ids),
                'submitted_at': datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
        submitted.append((cidx + 1, job_name, len(target_ids), path))
        print(f'  ✅ {job_name}  ({len(target_ids):,}건) → {path}')

        # ai_batch_job 컬럼에 마킹 (회수 추적용)
        conn = sqlite3.connect(os.environ.get('MARKETING_BOT_DB_PATH', 'db/marketing_data.db'))
        c = conn.cursor()
        placeholders = ','.join('?' * len(target_ids))
        c.execute(f'UPDATE viral_targets SET ai_batch_job=? WHERE id IN ({placeholders})',
                  [job_name] + target_ids)
        conn.commit()
        conn.close()

    print('\n' + '=' * 70)
    print(f'제출 완료: {len(submitted)}/{chunks_total} 청크')
    for idx, name, n, path in submitted:
        print(f'  chunk {idx:03d}: {name}  ({n:,}건)')
    print(f'\n다음 단계:')
    print(f'  python scripts/ai_ad_classify_status.py {out_dir}')
    print(f'  python scripts/ai_ad_classify_apply.py {out_dir}    # 모두 SUCCEEDED 후')


if __name__ == '__main__':
    main()
