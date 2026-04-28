"""
Content Gap Analyzer (BGE-M3 임베딩 기반)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

자사 콘텐츠 (qa_repository + 자기 한의원 viral_targets) vs
경쟁사 콘텐츠 (competitor_blog_activity)를 BGE-M3로 임베딩 비교.

코사인 유사도 < 0.5 → 갭 후보 (자사가 다루지 않는 주제)
Gemini로 시드 키워드 제안.

CLI:
  python scripts/content_gap_analyzer.py --status
  python scripts/content_gap_analyzer.py --top 30
  python scripts/content_gap_analyzer.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# setup_paths
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "marketing_bot_web" / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend_utils.logger import get_logger  # type: ignore
    logger = get_logger(__name__)
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("content_gap")

DB_PATH = _ROOT / "db" / "marketing_data.db"
SIM_THRESHOLD = 0.5  # 미만이면 갭

_BUSINESS_PROFILE: Dict[str, Any] = {}


def _load_business_profile() -> Dict[str, Any]:
    global _BUSINESS_PROFILE
    if _BUSINESS_PROFILE:
        return _BUSINESS_PROFILE
    try:
        with open(_ROOT / "config" / "business_profile.json", "r", encoding="utf-8") as f:
            _BUSINESS_PROFILE = json.load(f)
    except Exception:
        _BUSINESS_PROFILE = {}
    return _BUSINESS_PROFILE


def _is_self_target(title: str, url: str) -> bool:
    """business_profile.json::self_exclusion 매칭."""
    profile = _load_business_profile()
    se = profile.get("self_exclusion", {})
    if not se:
        return False
    text = (title or "") + " " + (url or "")
    text_l = text.lower()
    for kw in se.get("title_keywords", []):
        if kw.lower() in text_l:
            return True
    for pat in se.get("url_patterns", []):
        if pat.lower() in (url or "").lower():
            return True
    for au in se.get("blog_authors", []):
        if au.lower() in (url or "").lower():
            return True
    return False


def _table_exists(cursor: sqlite3.Cursor, name: str) -> bool:
    cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cursor.fetchone() is not None


def _ensure_gaps_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS content_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_topic TEXT NOT NULL,
            competitor_url TEXT,
            closest_self_url TEXT,
            similarity REAL,
            suggested_seed TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gaps_sim ON content_gaps(similarity, detected_at DESC)"
    )


def _fetch_self_corpus(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    """자사 콘텐츠 (qa_repository + 자기 한의원 viral_targets)."""
    items: List[Dict[str, Any]] = []

    if _table_exists(cur, "qa_repository"):
        cur.execute(
            "SELECT id, question_pattern, standard_answer FROM qa_repository LIMIT 500"
        )
        for row in cur.fetchall():
            qa_id, pat, ans = row
            text = f"{pat or ''} {ans or ''}".strip()
            if text:
                items.append({"source": "qa", "id": qa_id, "url": f"qa://{qa_id}", "text": text[:1500]})

    if _table_exists(cur, "viral_targets"):
        # title 기반으로 자기 한의원만
        cur.execute(
            "SELECT id, url, title, content_preview FROM viral_targets "
            "WHERE title IS NOT NULL LIMIT 1000"
        )
        for row in cur.fetchall():
            vid, url, title, preview = row
            if _is_self_target(title or "", url or ""):
                text = f"{title or ''} {preview or ''}".strip()
                if text:
                    items.append({"source": "self_blog", "id": vid, "url": url or "", "text": text[:1500]})

    return items


def _fetch_competitor_corpus(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    """경쟁사 블로그 활동."""
    if not _table_exists(cur, "competitor_blog_activity"):
        return []

    # 컬럼 확인
    cur.execute("PRAGMA table_info(competitor_blog_activity)")
    cols = {row[1] for row in cur.fetchall()}
    title_col = "post_title" if "post_title" in cols else ("title" if "title" in cols else None)
    url_col = "post_url" if "post_url" in cols else ("url" if "url" in cols else None)
    body_col = "content_preview" if "content_preview" in cols else ("preview" if "preview" in cols else None)
    if not title_col or not url_col:
        return []

    body_select = f", {body_col}" if body_col else ", ''"
    cur.execute(
        f"SELECT {title_col}, {url_col}{body_select} FROM competitor_blog_activity "
        f"WHERE {title_col} IS NOT NULL ORDER BY rowid DESC LIMIT 500"
    )
    items: List[Dict[str, Any]] = []
    for row in cur.fetchall():
        title, url = row[0], row[1]
        body = row[2] if len(row) > 2 else ""
        if not title:
            continue
        text = f"{title} {body or ''}".strip()
        items.append({"url": url, "title": title, "text": text[:1500]})
    return items


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """sentence-transformers BGE-M3 (qa_search.py와 동일 모델 재사용)."""
    from sentence_transformers import SentenceTransformer  # 지연 import

    import os
    model_id = os.getenv("MARKETING_BOT_EMBED_MODEL", "BAAI/bge-m3")
    logger.info(f"임베딩 모델 로드: {model_id}")
    model = SentenceTransformer(model_id)
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [list(map(float, e)) for e in embs]


def _cosine(a: List[float], b: List[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))  # 정규화 가정


def _suggest_seed(competitor_title: str) -> str:
    """Gemini로 시드 키워드 제안. 실패 시 빈 문자열."""
    try:
        from services.ai_client import ai_generate_json  # type: ignore
    except Exception as e:
        logger.warning(f"ai_client import 실패: {e}")
        return ""
    prompt = (
        "아래 경쟁사 블로그 제목을 보고, 우리 한의원이 다룰 만한 "
        "한국어 시드 키워드 1개를 JSON으로 제안해라.\n"
        f"제목: {competitor_title}\n"
        '응답 형식: {"seed": "키워드"}'
    )
    try:
        out = ai_generate_json(prompt, temperature=0.3, max_tokens=100)
        if isinstance(out, dict):
            return str(out.get("seed", "")).strip()
    except Exception as e:
        logger.debug(f"seed 제안 실패: {e}")
    return ""


def analyze_gaps(
    db_path: Path, top_n: int = 30, dry_run: bool = False, suggest: bool = True
) -> Dict[str, Any]:
    if not db_path.exists():
        return {"error": f"DB 없음: {db_path}"}

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        self_items = _fetch_self_corpus(cur)
        comp_items = _fetch_competitor_corpus(cur)

        if not self_items:
            return {"error": "자사 콘텐츠 corpus 비어있음 (qa_repository / viral_targets)"}
        if not comp_items:
            return {"error": "competitor_blog_activity 비어있음. 경쟁사 블로그 수집 먼저 실행."}

        logger.info(f"자사={len(self_items)} / 경쟁사={len(comp_items)} 임베딩 시작")

        self_embs = _embed_texts([it["text"] for it in self_items])
        comp_embs = _embed_texts([it["text"] for it in comp_items])

        gaps: List[Dict[str, Any]] = []
        for i, ce in enumerate(comp_embs):
            best_sim = -1.0
            best_idx = -1
            for j, se in enumerate(self_embs):
                sim = _cosine(ce, se)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = j
            if best_sim < SIM_THRESHOLD:
                gaps.append(
                    {
                        "competitor_topic": comp_items[i]["title"],
                        "competitor_url": comp_items[i]["url"],
                        "closest_self_url": self_items[best_idx]["url"] if best_idx >= 0 else "",
                        "similarity": round(best_sim, 4),
                    }
                )

        gaps.sort(key=lambda g: g["similarity"])
        gaps = gaps[:top_n]

        # Gemini 시드 제안
        if suggest:
            for g in gaps:
                g["suggested_seed"] = _suggest_seed(g["competitor_topic"])

        # 적재
        if not dry_run and gaps:
            _ensure_gaps_table(cur)
            for g in gaps:
                cur.execute(
                    """
                    INSERT INTO content_gaps
                    (competitor_topic, competitor_url, closest_self_url,
                     similarity, suggested_seed)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        g["competitor_topic"],
                        g["competitor_url"],
                        g["closest_self_url"],
                        g["similarity"],
                        g.get("suggested_seed", ""),
                    ),
                )
            conn.commit()

        return {
            "self_corpus": len(self_items),
            "competitor_corpus": len(comp_items),
            "gaps_count": len(gaps),
            "threshold": SIM_THRESHOLD,
            "top_n": top_n,
            "dry_run": dry_run,
            "gaps": gaps,
        }
    finally:
        if conn is not None:
            conn.close()


def status(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {"error": "DB 없음"}
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        has_comp = _table_exists(cur, "competitor_blog_activity")
        has_qa = _table_exists(cur, "qa_repository")
        has_gaps = _table_exists(cur, "content_gaps")
        n = 0
        latest = None
        if has_gaps:
            cur.execute("SELECT COUNT(*), MAX(detected_at) FROM content_gaps")
            n, latest = cur.fetchone()
        return {
            "competitor_blog_activity": has_comp,
            "qa_repository": has_qa,
            "content_gaps_table": has_gaps,
            "gaps_count": int(n or 0),
            "latest_run": latest,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="콘텐츠 갭 분석")
    parser.add_argument("--top", type=int, default=30, help="상위 갭 N개 (기본 30)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-seed", action="store_true", help="Gemini 시드 제안 비활성")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(DB_PATH), ensure_ascii=False, indent=2))
        return 0

    result = analyze_gaps(
        DB_PATH, top_n=args.top, dry_run=args.dry_run, suggest=not args.no_seed
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
