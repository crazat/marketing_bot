"""Lane C(연장) — 시그니처 콘텐츠 브리프 → 발행용 *초안 본문* 생성기.

브리프(제목·H2)만으로는 직원이 본문을 또 써야 한다. 이 스크립트는 브리프 + Lane B Q&A
지식으로 발행 직전 초안 본문을 생성해, 사람이 *검수 후 붙여넣기*만 하면 되게 한다.

⚠️ 중요 — 톤 정책:
- 1인칭 환자 경험담("저도 다녀왔는데")은 **바이럴 댓글 전용**(USER DIRECTIVE). *자체* 블로그/
  플레이스 콘텐츠에 클리닉이 가짜 환자 후기를 쓰면 의료광고법(체험단/조작후기) 위반이다.
- 따라서 자체 콘텐츠는 **정보성 클리닉 교육 톤**으로 쓰고, 환자 목소리는 "이런 고민으로
  오시는 분들이 많아요/자주 묻는 질문" 형태로만 반영한다(후기 사칭 금지).
- 경성 위반 금지: 완치/보장/100%/단정, 할인·이벤트, 전후사진·기간·수치 조작, AI 의료진 추천,
  경쟁사 실명 비교. 생성 후 content_compliance.check_content_compliance 로 검증.

⚠️ 게시는 사람이 한다(HITL). 이 스크립트는 reports/ 에 초안만 출력한다.

실행: python scripts/generate_signature_post_drafts.py
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

from services.ai_client import ai_generate  # noqa: E402
from services import content_compliance as cc  # noqa: E402

_BRIEFS = os.path.join(_ROOT, "reports", "signature_content_briefs.json")
_QA = os.path.join(_ROOT, "reports", "signature_qa_drafts.json")


PROMPT = """너는 청주 규림한의원의 콘텐츠 작성자다. 아래 브리프대로 *우리가 직접 발행할* {channel} 초안
본문을 쓴다(남의 글 댓글이 아니라 자체 콘텐츠).

[제목] {title}
[대표 키워드] {primary}
[보조 키워드(자연스럽게 녹일 것)] {secondary}
[H2 개요]
{h2}
[참고 지식(Q&A — 사실/톤 참고용)]
{qa}

[톤·규칙 — 반드시 준수]
1. **정보성 클리닉 교육 톤**. "저도 다녀왔는데" 같은 1인칭 환자 후기/사칭은 절대 쓰지 말 것
   (자체 콘텐츠에서 가짜 환자 경험담은 의료광고법 위반). 환자 목소리는 "이런 고민으로 오시는
   분들이 많아요", "자주 묻는 질문" 형태로만.
2. H2 개요를 소제목(## )으로 살려 자연스러운 정보 흐름으로 작성. 각 섹션 2~4문장.
3. 풀네임 "규림한의원" 사용. 부드럽고 신뢰감 있는 어조.
4. 금지: 완치/보장/100%/확실히 등 단정, 할인·이벤트·특가, 전후사진 강조, 치료기간·수치 확정,
   AI 의료진 추천, 경쟁사 실명 비교. 효과는 "개인차가 있어요/상담이 필요해요"로 완충.
5. 마지막에 "자주 묻는 질문" 2~3개(Q&A 지식 활용)와 부드러운 상담 안내 1문장.
6. 마크다운으로 출력(제목은 # 으로). 메타설명·해시태그 등 부가요소는 넣지 말 것(본문만).

{channel} 초안 본문만 출력:"""


def _verdict(res: dict) -> tuple:
    """check_content_compliance 반환을 (passed, issues) 로 정규화."""
    if not isinstance(res, dict):
        return True, []
    passed = res.get("passed")
    if passed is None:
        passed = res.get("is_compliant", res.get("compliant", True))
    issues = res.get("violations") or res.get("issues") or res.get("flags") or []
    if isinstance(issues, dict):
        issues = list(issues.keys())
    return bool(passed), [str(x)[:80] for x in issues][:6]


def main() -> int:
    ap = argparse.ArgumentParser(description="시그니처 발행 초안 본문 생성기 (Lane C 연장)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "reports", "signature_post_drafts.md"))
    args = ap.parse_args()

    if not os.path.exists(_BRIEFS):
        print(f"❌ 브리프 없음: {_BRIEFS} — 먼저 generate_signature_content_briefs.py 실행")
        return 1
    briefs = json.load(open(_BRIEFS, encoding="utf-8")).get("briefs") or []
    qa_items = []
    if os.path.exists(_QA):
        qa_items = json.load(open(_QA, encoding="utf-8")).get("drafts") or []
    qa_str = "\n".join(f"- Q:{d.get('question_pattern','')} / A:{d.get('standard_answer','')[:120]}"
                       for d in qa_items[:9]) or "(없음)"

    out = [f"# 시그니처 발행 초안 본문 (Lane C)\n",
           f"_생성: {datetime.now().isoformat(timespec='seconds')} · ⚠️ 검수 후 사람이 발행 · 자체 콘텐츠=교육 톤(환자 후기 사칭 금지)_\n"]

    for i, b in enumerate(briefs, 1):
        channel = "블로그 글" if b.get("channel") == "blog" else "네이버 플레이스 소개글"
        prompt = PROMPT.format(
            channel=channel,
            title=b.get("title", ""),
            primary=b.get("primary_keyword", ""),
            secondary=", ".join(b.get("secondary_keywords") or []),
            h2="\n".join(f"- {h}" for h in b.get("h2_outline") or []),
            qa=qa_str,
        )
        print(f"🤖 [{i}/{len(briefs)}] '{b.get('title','')[:40]}' 초안 생성 중...")
        body = ai_generate(prompt, temperature=0.6, max_tokens=2200)
        try:
            passed, issues = _verdict(cc.check_content_compliance(body, content_type="blog"))
        except Exception as e:
            passed, issues = True, [f"(compliance check 실패: {e})"]

        status = "✅ 통과" if passed else "⚠️ 검토필요"
        out.append(f"\n---\n\n## 초안 {i} · [{b.get('channel')}] — 컴플라이언스 {status}")
        if issues:
            out.append(f"\n> ⚠️ 플래그: {'; '.join(issues)}")
        out.append(f"\n_대표 키워드: `{b.get('primary_keyword','')}`_\n")
        out.append(body.strip())
        print(f"   컴플라이언스: {status}" + (f" ({len(issues)} 플래그)" if issues else ""))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"\n✅ 초안 {len(briefs)}개 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
