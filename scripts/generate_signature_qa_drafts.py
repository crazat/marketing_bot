"""Lane B — 시그니처 축(흉터/안면비대칭) Q&A 지식 시딩 *드래프트 생성기*.

배경: qa_repository 에 흉터/안면비대칭 Q&A 가 0행이라, 시그니처 리드를 발견해도 댓글
드래프터의 BGE-M3 RAG 가 매칭할 참고지식이 없다(약한/차단 댓글 → 낮은 승인율). 이 스크립트는
규림한의원(청주) 시그니처 치료(새살침=흉터, 안면비대칭 교정) 지식을 AI 로 초안 생성해
``reports/signature_qa_drafts.json`` 에 적재한다.

⚠️ 이 스크립트는 **DB 에 쓰지 않는다**. 사람이 드래프트를 검수한 뒤 ``scripts/seed_signature_qa.py``
로만 qa_repository 에 적재한다(DML = 마이그레이션 스크립트로만, HITL 큐레이션 원칙).

생성 톤/컴플라이언스(1인칭 정책 USER DIRECTIVE 준수):
- standard_answer 는 댓글 드래프터가 1인칭 환자 경험담으로 변환할 수 있는 정보성 참고답변.
- 풀네임 "규림한의원" 사용. 초성(ㄱㄹ)·'거기' 익명화 금지.
- 경성 위반 금지: 완치/보장/단정, 할인/이벤트, 전후·기간·수치 조작, AI 의료진 추천 비교.

실행: python scripts/generate_signature_qa_drafts.py [--count 10]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "marketing_bot_web", "backend"))

from services.ai_client import ai_generate_json  # noqa: E402

# 규림 시그니처 치료축 서브토픽 — gyulim_keyword_profile 어휘 기반(단일 소스 참조).
SIGNATURE_TOPICS = {
    "흉터/여드름흉터": [
        "여드름흉터(패인 자국·구덩이) 한방 치료",
        "새살침(흉터 침 치료)이 뭔지·효과",
        "모공흉터·넓어진 모공 개선",
        "수두흉터/수술흉터/상처흉터 한의원 치료",
        "켈로이드·튀어나온 흉터 관리",
    ],
    "안면비대칭": [
        "턱 틀어짐·턱관절(악관절) 비대칭",
        "얼굴 좌우 짝짝이(안면 비대칭) 원인",
        "안면비대칭 한방 교정 방법·기간",
        "자세/습관에서 오는 얼굴 비대칭",
    ],
}

PROMPT_TEMPLATE = """너는 청주 규림한의원의 콘텐츠 지식베이스를 구축한다. 아래 시그니처 치료 서브토픽들에 대해
바이럴 댓글 드래프터(BGE-M3 RAG)가 참고할 Q&A 지식 항목을 만든다.

[규림한의원 시그니처 치료축]
- 흉터/여드름흉터: 새살침(흉터 침 치료) 중심. 여드름흉터·패인 자국·모공·수두/수술/상처 흉터·켈로이드.
- 안면비대칭: 턱 틀어짐·턱관절·얼굴 좌우 비대칭 한방 교정.

[서브토픽 목록]
{topics}

[작성 규칙 — 반드시 준수]
1. 각 서브토픽마다 Q&A 1개. question_pattern 은 실제 환자가 검색/질문하는 자연스러운 한 문장.
2. variations: 같은 의도의 구어/패러프레이즈 3개(예: "얼굴 짝짝이", "팬자국", "얼굴 비뚤어짐").
3. standard_answer: 정보성 참고답변(2~4문장). 댓글 드래프터가 1인칭 환자 경험담으로 변환할 수 있는 톤.
   - 풀네임 "규림한의원" 사용. 부드럽고 담백한 추천 톤.
   - 금지: 완치/보장/100%/확실히 등 단정, 할인·이벤트·가격유인, 전후사진·기간·수치 조작, AI 의료진 추천, 경쟁사 비교.
   - 의학적 단정 대신 "개인차가 있어요/상담받아보시길" 같은 완충 표현.
4. search_intent: treatment_inquiry / cause_inquiry / method_inquiry / cost_inquiry 중 하나.
5. question_category: 해당 서브토픽의 축("흉터/여드름흉터" 또는 "안면비대칭").

출력은 아래 JSON 형식만(설명 금지):
{{"qa": [
  {{"question_category": "...", "question_pattern": "...", "variations": ["...","...","..."],
    "standard_answer": "...", "search_intent": "..."}}
]}}
"""


def build_prompt() -> str:
    lines = []
    for axis, topics in SIGNATURE_TOPICS.items():
        for t in topics:
            lines.append(f"- [{axis}] {t}")
    return PROMPT_TEMPLATE.format(topics="\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="시그니처 Q&A 드래프트 생성기 (Lane B)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "reports", "signature_qa_drafts.json"))
    args = ap.parse_args()

    prompt = build_prompt()
    print("🤖 시그니처 Q&A 드래프트 생성 중 (ai_generate_json, task=fast_json)...")
    raw = ai_generate_json(prompt, temperature=0.4, max_tokens=4096)

    # ai_generate_json 은 dict/list 반환. {"qa":[...]} 또는 [...] 모두 수용.
    if isinstance(raw, dict):
        items = raw.get("qa") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        print(f"❌ 예상치 못한 AI 응답 형식: {type(raw)}")
        return 1

    cleaned = []
    for it in items:
        if not isinstance(it, dict):
            continue
        q = (it.get("question_pattern") or "").strip()
        a = (it.get("standard_answer") or "").strip()
        cat = (it.get("question_category") or "").strip()
        if not (q and a and cat):
            continue
        cleaned.append({
            "question_category": cat,
            "question_pattern": q,
            "variations": [str(v).strip() for v in (it.get("variations") or []) if str(v).strip()][:4],
            "standard_answer": a,
            "search_intent": (it.get("search_intent") or "treatment_inquiry").strip(),
        })

    if not cleaned:
        print("❌ 유효한 Q&A 드래프트가 생성되지 않았습니다.")
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "needs_review": True,
        "note": "사람 검수 후 scripts/seed_signature_qa.py 로만 qa_repository 적재. 자동 적재 금지.",
        "count": len(cleaned),
        "drafts": cleaned,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(cleaned)}개 Q&A 드래프트 생성 → {args.out}")
    print("   다음: 파일 검수 → python scripts/seed_signature_qa.py --apply")
    for d in cleaned:
        print(f"   · [{d['question_category']}] {d['question_pattern'][:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
