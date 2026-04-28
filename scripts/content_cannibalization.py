"""
Content Cannibalization Detector
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

같은 검색어에 자사 URL이 2개 이상 클릭을 나눠가지면 카니발리제이션 후보.

데이터 소스: inbound_search_queries 테이블 (Search Console 동기화 가정)
  - query, landing_url, clicks, impressions, observed_at

테이블 없으면 graceful skip.

CLI:
  python scripts/content_cannibalization.py --status
  python scripts/content_cannibalization.py --days 28 --min-clicks 5
  python scripts/content_cannibalization.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# setup_paths import (sys.path 자동 설정)
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "marketing_bot_web" / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend_utils.logger import get_logger  # type: ignore
    logger = get_logger(__name__)
except Exception:  # 단독 실행 폴백
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("cannibalization")

DB_PATH = _ROOT / "db" / "marketing_data.db"

# 점유율 임계값: 2위 URL이 이 비율 이상 가져갈 때만 카니발 후보
SHARE_THRESHOLD = 0.10
SEVERITY_TIERS = [
    (0.40, "high"),    # 2위 URL이 40% 이상 → 심각
    (0.20, "medium"),
    (0.10, "low"),
]


def _ensure_findings_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cannibalization_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            competing_urls TEXT NOT NULL,
            total_clicks INTEGER,
            measured_period_start TEXT,
            measured_period_end TEXT,
            severity TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cannibal_query ON cannibalization_findings(query)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cannibal_severity ON cannibalization_findings(severity, detected_at DESC)"
    )


def _table_exists(cursor: sqlite3.Cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    )
    return cursor.fetchone() is not None


def _classify_severity(top_share: float) -> str:
    for thresh, tier in SEVERITY_TIERS:
        if top_share >= thresh:
            return tier
    return "low"


def detect_cannibalization(
    db_path: Path,
    days: int,
    min_clicks: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """카니발리제이션 후보 검출 → cannibalization_findings 적재."""
    if not db_path.exists():
        return {"error": f"DB 없음: {db_path}", "findings": []}

    end = datetime.now()
    start = end - timedelta(days=days)

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if not _table_exists(cur, "inbound_search_queries"):
            logger.warning(
                "inbound_search_queries 테이블 없음 — Search Console 동기화 모듈(예정) 미적용. "
                "스킵."
            )
            return {
                "skipped": True,
                "reason": "inbound_search_queries 테이블 미존재 (GSC 동기화 필요)",
                "findings": [],
            }

        _ensure_findings_table(cur)

        cur.execute(
            """
            SELECT query, landing_url, SUM(clicks) AS clicks, SUM(impressions) AS impressions
            FROM inbound_search_queries
            WHERE observed_at >= ? AND observed_at <= ?
              AND query IS NOT NULL AND landing_url IS NOT NULL
            GROUP BY query, landing_url
            """,
            (start.isoformat(), end.isoformat()),
        )
        rows = cur.fetchall()

        # query → list of (url, clicks)
        agg: Dict[str, List[Dict[str, int]]] = {}
        for r in rows:
            q = r["query"]
            agg.setdefault(q, []).append(
                {"url": r["landing_url"], "clicks": int(r["clicks"] or 0)}
            )

        findings: List[Dict[str, Any]] = []
        for query, url_list in agg.items():
            total = sum(u["clicks"] for u in url_list)
            if total < min_clicks:
                continue
            url_list.sort(key=lambda u: u["clicks"], reverse=True)
            if len(url_list) < 2:
                continue

            # 2위 점유율 (가장 작은 경쟁자 중 큰 것)
            second = url_list[1]
            second_share = (second["clicks"] / total) if total else 0.0
            if second_share < SHARE_THRESHOLD:
                continue

            top_share = url_list[0]["clicks"] / total
            severity = _classify_severity(second_share)

            findings.append(
                {
                    "query": query,
                    "competing_urls": url_list,
                    "total_clicks": total,
                    "top_share": round(top_share, 3),
                    "second_share": round(second_share, 3),
                    "severity": severity,
                }
            )

        # severity 정렬
        sev_rank = {"high": 0, "medium": 1, "low": 2}
        findings.sort(key=lambda f: (sev_rank.get(f["severity"], 9), -f["total_clicks"]))

        # 적재 (dry-run 아니면)
        if not dry_run and findings:
            for f in findings:
                cur.execute(
                    """
                    INSERT INTO cannibalization_findings
                    (query, competing_urls, total_clicks,
                     measured_period_start, measured_period_end, severity)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f["query"],
                        json.dumps(f["competing_urls"], ensure_ascii=False),
                        f["total_clicks"],
                        start.date().isoformat(),
                        end.date().isoformat(),
                        f["severity"],
                    ),
                )
            conn.commit()

        return {
            "period_days": days,
            "min_clicks": min_clicks,
            "queries_examined": len(agg),
            "findings_count": len(findings),
            "findings": findings,
            "dry_run": dry_run,
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
        has_source = _table_exists(cur, "inbound_search_queries")
        has_findings = _table_exists(cur, "cannibalization_findings")
        n_findings = 0
        latest = None
        if has_findings:
            cur.execute("SELECT COUNT(*), MAX(detected_at) FROM cannibalization_findings")
            n_findings, latest = cur.fetchone()
        return {
            "source_table_present": has_source,
            "findings_table_present": has_findings,
            "findings_count": int(n_findings or 0),
            "latest_run": latest,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="콘텐츠 카니발리제이션 검출")
    parser.add_argument("--days", type=int, default=28, help="조회 기간 (기본 28)")
    parser.add_argument("--min-clicks", type=int, default=5, help="최소 클릭 수 (기본 5)")
    parser.add_argument("--status", action="store_true", help="상태만 조회")
    parser.add_argument("--dry-run", action="store_true", help="DB 적재하지 않음")
    args = parser.parse_args()

    if args.status:
        s = status(DB_PATH)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    result = detect_cannibalization(
        DB_PATH, days=args.days, min_clicks=args.min_clicks, dry_run=args.dry_run
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("skipped"):
        print(
            "\n[안내] inbound_search_queries 테이블이 없습니다. "
            "Search Console 동기화 모듈을 먼저 실행하세요.",
            file=sys.stderr,
        )
        return 0

    n = result.get("findings_count", 0)
    if n == 0:
        print("\n카니발리제이션 후보 없음.", file=sys.stderr)
    else:
        print(f"\n카니발리제이션 후보 {n}건 검출됨.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
