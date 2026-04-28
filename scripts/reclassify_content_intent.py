"""
Content Search Intent Reclassifier
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

자사 콘텐츠 (qa_repository + 자기 한의원 viral_targets)를
7-tier intent로 자동 재분류 (Gemini Flash Lite, JSON 모드).

7-tier (pathfinder_v3_complete::_classify_intent와 동일):
  red_flag, validation, comparison, transactional, commercial,
  informational, navigational

CLI:
  python scripts/reclassify_content_intent.py --status
  python scripts/reclassify_content_intent.py --limit 50
  python scripts/reclassify_content_intent.py --force --limit 100
  python scripts/reclassify_content_intent.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    logger = logging.getLogger("reclassify_intent")

DB_PATH = _ROOT / "db" / "marketing_data.db"

VALID_INTENTS = {
    "red_flag",
    "validation",
    "comparison",
    "transactional",
    "commercial",
    "informational",
    "navigational",
}

_PROFILE: Dict[str, Any] = {}


def _load_profile() -> Dict[str, Any]:
    global _PROFILE
    if _PROFILE:
        return _PROFILE
    try:
        with open(_ROOT / "config" / "business_profile.json", "r", encoding="utf-8") as f:
            _PROFILE = json.load(f)
    except Exception:
        _PROFILE = {}
    return _PROFILE


def _is_self_target(title: str, url: str) -> bool:
    profile = _load_profile()
    se = profile.get("self_exclusion", {})
    if not se:
        return False
    text_l = ((title or "") + " " + (url or "")).lower()
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


def _ensure_search_intent_columns(conn: sqlite3.Connection) -> None:
    """qa_repository / viral_targets에 search_intent 컬럼 보강."""
    cur = conn.cursor()

    def _has_col(table: str, col: str) -> bool:
        cur.execute(f"PRAGMA table_info({table})")
        return any(r[1] == col for r in cur.fetchall())

    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qa_repository'")
    if cur.fetchone() and not _has_col("qa_repository", "search_intent"):
        cur.execute("ALTER TABLE qa_repository ADD COLUMN search_intent TEXT")
        logger.info("qa_repository: search_intent 컬럼 추가됨")

    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='viral_targets'")
    if cur.fetchone() and not _has_col("viral_targets", "search_intent"):
        cur.execute("ALTER TABLE viral_targets ADD COLUMN search_intent TEXT")
        logger.info("viral_targets: search_intent 컬럼 추가됨")

    conn.commit()


def _classify_via_ai(text: str) -> Optional[str]:
    """Gemini ai_generate_json 호출. 실패 시 None."""
    try:
        from services.ai_client import ai_generate_json  # type: ignore
    except Exception as e:
        logger.error(f"ai_client import 실패: {e}")
        return None

    prompt = (
        "아래 한국어 콘텐츠의 검색 의도를 7개 중 1개로 분류해라.\n\n"
        "분류 정의:\n"
        "- red_flag: 부작용/위험/논란 등 부정 정보 탐색\n"
        "- validation: 진짜/솔직/실제 등 진위 검증\n"
        "- comparison: vs/비교/차이\n"
        "- transactional: 가격/예약/할인/이벤트 (구매 의도)\n"
        "- commercial: 추천/순위/베스트/잘하는 (선호 결정)\n"
        "- informational: 방법/효과/원인/증상 (지식 탐색)\n"
        "- navigational: 위치/주소/전화/영업시간\n\n"
        f"콘텐츠: {text[:500]}\n\n"
        '응답 형식: {"intent": "분류값"}'
    )
    try:
        out = ai_generate_json(prompt, temperature=0.1, max_tokens=80)
        if isinstance(out, dict):
            v = str(out.get("intent", "")).strip().lower()
            if v in VALID_INTENTS:
                return v
            logger.debug(f"잘못된 intent 반환: {v}")
    except Exception as e:
        logger.debug(f"AI 분류 실패: {e}")
    return None


def _fetch_targets(
    conn: sqlite3.Connection, limit: int, force: bool
) -> List[Tuple[str, int, str, str]]:
    """반환: list of (table, id, text, current_intent)."""
    cur = conn.cursor()
    out: List[Tuple[str, int, str, str]] = []

    # qa_repository
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qa_repository'")
    if cur.fetchone():
        where = "" if force else "WHERE search_intent IS NULL OR search_intent = ''"
        cur.execute(
            f"SELECT id, question_pattern, standard_answer, COALESCE(search_intent,'') "
            f"FROM qa_repository {where} ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        for row in cur.fetchall():
            qa_id, pat, ans, cur_intent = row
            text = f"{pat or ''} | {ans or ''}".strip()
            if text:
                out.append(("qa_repository", qa_id, text, cur_intent or ""))

    # viral_targets — 자기 한의원만
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='viral_targets'")
    if cur.fetchone() and len(out) < limit:
        remaining = limit - len(out)
        where = "title IS NOT NULL"
        if not force:
            where += " AND (search_intent IS NULL OR search_intent = '')"
        cur.execute(
            f"SELECT id, url, title, COALESCE(content_preview, ''), "
            f"COALESCE(search_intent, '') FROM viral_targets WHERE {where} "
            f"ORDER BY discovered_at DESC LIMIT ?",
            (remaining * 3,),  # self_exclusion 필터로 솎이므로 여유롭게
        )
        for row in cur.fetchall():
            vid, url, title, preview, cur_intent = row
            if not _is_self_target(title or "", url or ""):
                continue
            text = f"{title or ''} | {preview or ''}".strip()
            if text:
                out.append(("viral_targets", vid, text, cur_intent or ""))
            if len(out) >= limit:
                break

    return out[:limit]


def reclassify(
    db_path: Path, limit: int = 50, force: bool = False, dry_run: bool = False
) -> Dict[str, Any]:
    if not db_path.exists():
        return {"error": f"DB 없음: {db_path}"}

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(db_path))
        _ensure_search_intent_columns(conn)
        cur = conn.cursor()

        targets = _fetch_targets(conn, limit, force)
        if not targets:
            return {"processed": 0, "message": "분류 대상 없음", "distribution": {}}

        distribution: Counter = Counter()
        changes: List[Dict[str, Any]] = []
        success = 0
        failed = 0

        for table, row_id, text, prev_intent in targets:
            new_intent = _classify_via_ai(text)
            if not new_intent:
                failed += 1
                continue
            success += 1
            distribution[new_intent] += 1
            changes.append(
                {
                    "table": table,
                    "id": row_id,
                    "previous": prev_intent or None,
                    "new": new_intent,
                    "preview": text[:80],
                }
            )
            if not dry_run:
                cur.execute(
                    f"UPDATE {table} SET search_intent = ? WHERE id = ?",
                    (new_intent, row_id),
                )

        if not dry_run:
            conn.commit()

        return {
            "processed": len(targets),
            "success": success,
            "failed": failed,
            "distribution": dict(distribution),
            "force": force,
            "dry_run": dry_run,
            "changes_sample": changes[:10],
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
        result: Dict[str, Any] = {}

        for table in ("qa_repository", "viral_targets"):
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if not cur.fetchone():
                result[table] = {"exists": False}
                continue
            cur.execute(f"PRAGMA table_info({table})")
            has_col = any(r[1] == "search_intent" for r in cur.fetchall())
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total = cur.fetchone()[0]
            classified = 0
            dist: Dict[str, int] = {}
            if has_col:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE search_intent IS NOT NULL "
                    f"AND search_intent != ''"
                )
                classified = cur.fetchone()[0]
                cur.execute(
                    f"SELECT search_intent, COUNT(*) FROM {table} "
                    f"WHERE search_intent IS NOT NULL AND search_intent != '' "
                    f"GROUP BY search_intent"
                )
                dist = {r[0]: r[1] for r in cur.fetchall()}
            result[table] = {
                "exists": True,
                "search_intent_column": has_col,
                "total": total,
                "classified": classified,
                "distribution": dist,
            }
        return result
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="콘텐츠 검색 의도 자동 재분류")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true", help="이미 분류된 것도 재분류")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(DB_PATH), ensure_ascii=False, indent=2))
        return 0

    result = reclassify(DB_PATH, limit=args.limit, force=args.force, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
