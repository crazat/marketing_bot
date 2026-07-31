"""Lane C — 시그니처 축 자체 콘텐츠(블로그/플레이스) 브리프 생성기.

진단: 시그니처 축(흉터/안면비대칭)의 골든큐 전환이 구조적으로 막힌 진짜 이유는 로컬
환자 글의 희소성이다(댓글-헌팅은 수요측 채널). 지속적 차별자는 규림 *자체* 콘텐츠가
로컬 SERP 를 점유하는 것 — Pathfinder 가 찾은 시그니처 S/A 키워드는 '댓글 타겟'이 아니라
'자체 콘텐츠 SEO 타겟'이다. 이 스크립트는 그 키워드 풀 + Lane B Q&A 지식을 묶어
블로그/네이버플레이스 포스트 브리프(제목·H2·키워드·1인칭 경험 섹션·내부링크)를 만든다.

⚠️ 게시는 사람이 한다(HITL). 이 스크립트는 reports/ 에 브리프만 출력한다(자동 게시 금지).

실행: python scripts/generate_signature_content_briefs.py
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "marketing_bot_web", "backend"))

from services.ai_client import ai_generate_json  # noqa: E402

_DB = os.path.join(_ROOT, "db", "marketing_data.db")
_QA = os.path.join(_ROOT, "reports", "signature_qa_drafts.json")

SIGNATURE_AXES = ("흉터/여드름흉터", "안면비대칭")
# 축별 pillar(기둥 콘텐츠) 시드 — 롱테일을 묶는 광범위 rankable 주제.
PILLAR_SEEDS = {
    "흉터/여드름흉터": ["청주 여드름흉터 새살침 치료", "청주 패인흉터·모공흉터 한방 관리"],
    "안면비대칭": ["청주 안면비대칭 한방 교정", "청주 턱틀어짐·턱관절 비대칭"],
}


def _load_keyword_pool() -> dict:
    conn = sqlite3.connect(_DB)
    try:
        conn.row_factory = sqlite3.Row
        pool = {}
        for ax in SIGNATURE_AXES:
            rows = conn.execute(
                """
                SELECT keyword, grade, search_volume
                FROM keyword_insights
                WHERE category = ? AND grade IN ('S', 'A') AND COALESCE(business_core, 0) = 1
                ORDER BY search_volume DESC, kei DESC
                LIMIT 25
                """,
                (ax,),
            ).fetchall()
            pool[ax] = [r["keyword"] for r in rows]
        return pool
    finally:
        conn.close()


def _load_qa_knowledge() -> list:
    if not os.path.exists(_QA):
        return []
    try:
        payload = json.load(open(_QA, encoding="utf-8"))
        return [
            {"q": d.get("question_pattern", ""), "a": d.get("standard_answer", "")}
            for d in (payload.get("drafts") or [])
        ]
    except Exception:
        return []


PROMPT = """너는 청주 규림한의원의 로컬 SEO 콘텐츠 전략가다. 아래 시그니처 치료축의 키워드 풀과
Q&A 지식을 묶어, 규림 *자체* 블로그/네이버플레이스 포스트 브리프를 만든다(댓글이 아니라 우리가
직접 발행할 콘텐츠).

[pillar 주제(축별)]
{pillars}

[실제 키워드 풀 — secondary_keywords 는 여기서 고를 것]
{pool}

[Q&A 지식(참고 톤/사실)]
{qa}

[작성 규칙]
1. pillar 주제마다 브리프 1개.
2. 각 브리프: channel("blog" 또는 "place"), primary_keyword(pillar의 대표 청주 로컬 키워드),
   title(클릭되는 한글 제목·지역명 포함), meta_description(80~110자),
   h2_outline(4~6개 H2 소제목·자연스러운 정보 흐름),
   secondary_keywords(키워드 풀에서 3~6개·롱테일 흡수),
   first_person_section_hint(1인칭 환자 경험담 섹션을 어떻게 녹일지 한 줄 가이드. "저도 규림한의원
   다녀왔는데..." 톤. 풀네임 규림한의원 유지),
   internal_link_hints(2~3개·연결하면 좋은 다른 글 주제),
   compliance_notes(이 주제에서 특히 조심할 의료광고법 포인트 1~2개).
3. 금지(콘텐츠 자체에 들어가면 안 되는 것): 완치/보장/100%/단정, 할인·이벤트, 전후사진 강조,
   기간·수치 조작, AI 의료진 추천, 경쟁사 실명 비교. compliance_notes 에 명시.

출력은 JSON 만:
{{"briefs": [
  {{"channel":"...","primary_keyword":"...","title":"...","meta_description":"...",
    "h2_outline":["...","..."],"secondary_keywords":["..."],
    "first_person_section_hint":"...","internal_link_hints":["..."],"compliance_notes":["..."]}}
]}}
"""


def _to_markdown(briefs: list, generated_at: str) -> str:
    out = [f"# 시그니처 축 콘텐츠 브리프 (Lane C)\n", f"_생성: {generated_at} · 게시는 사람이(HITL)_\n"]
    for i, b in enumerate(briefs, 1):
        out.append(f"\n## {i}. [{b.get('channel','?')}] {b.get('title','')}")
        out.append(f"\n- **primary_keyword**: `{b.get('primary_keyword','')}`")
        out.append(f"- **meta**: {b.get('meta_description','')}")
        sk = ", ".join(f"`{k}`" for k in b.get("secondary_keywords") or [])
        out.append(f"- **secondary_keywords**: {sk}")
        out.append("- **H2 개요**:")
        for h in b.get("h2_outline") or []:
            out.append(f"  - {h}")
        out.append(f"- **1인칭 경험 섹션**: {b.get('first_person_section_hint','')}")
        il = "; ".join(b.get("internal_link_hints") or [])
        out.append(f"- **내부링크**: {il}")
        cn = "; ".join(b.get("compliance_notes") or [])
        out.append(f"- **⚠️ 컴플라이언스**: {cn}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="시그니처 콘텐츠 브리프 생성기 (Lane C)")
    ap.add_argument("--out-json", default=os.path.join(_ROOT, "reports", "signature_content_briefs.json"))
    ap.add_argument("--out-md", default=os.path.join(_ROOT, "reports", "signature_content_briefs.md"))
    args = ap.parse_args()

    pool = _load_keyword_pool()
    qa = _load_qa_knowledge()
    pillars = "\n".join(f"- [{ax}] " + " / ".join(seeds) for ax, seeds in PILLAR_SEEDS.items())
    pool_str = "\n".join(f"[{ax}] " + ", ".join(kws[:18]) for ax, kws in pool.items())
    qa_str = "\n".join(f"- Q: {x['q']}\n  A: {x['a']}" for x in qa[:9]) or "(없음)"

    prompt = PROMPT.format(pillars=pillars, pool=pool_str, qa=qa_str)
    print("🤖 시그니처 콘텐츠 브리프 생성 중 (ai_generate_json)...")
    raw = ai_generate_json(prompt, temperature=0.5, max_tokens=4096)
    briefs = raw.get("briefs") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    briefs = [b for b in (briefs or []) if isinstance(b, dict) and b.get("title")]
    if not briefs:
        print("❌ 유효한 브리프가 생성되지 않았습니다.")
        return 1

    generated_at = datetime.now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    json.dump(
        {"generated_at": generated_at, "count": len(briefs), "briefs": briefs},
        open(args.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2,
    )
    open(args.out_md, "w", encoding="utf-8").write(_to_markdown(briefs, generated_at))

    print(f"✅ {len(briefs)}개 브리프 생성")
    print(f"   · JSON: {args.out_json}")
    print(f"   · MD:   {args.out_md}")
    for b in briefs:
        print(f"   · [{b.get('channel')}] {b.get('title','')[:50]} → {b.get('primary_keyword','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
