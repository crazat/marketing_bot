#!/usr/bin/env python
"""레거시/비표준 category 라벨을 콘텐츠 재탐지로 표준 진료축으로 정정.

배경(2026-06-19): 일부 viral_targets 의 stored `category` 가 분리 이전 레거시 라벨
(`피부`, `비대칭/교정`, `호흡기` 등)로 남아 있다. 현재 코드는 신규 행에 표준 라벨을
쓰지만, 과거 행 + 재발견 보존 때문에 레거시 라벨이 잔류한다. 이 라벨은
- `피부` 안에 실제 SCAR(흉터/여드름흉터, 시그니처 축) 글이 숨어 있고,
- `비대칭/교정` 은 대부분 체형교정인데 normalize_category 는 손실적으로 안면비대칭으로
  매핑한다(블라인드 매핑 위험).
그래서 라벨 블라인드 매핑이 아니라 **시스템 자체의 detect_category(콘텐츠 재탐지)** 로
정정한다 — 신규 행과 동일한 탐지 로직이므로 일관적. 표준 라벨 행은 건드리지 않는다.

안전장치: 실행 전 자동 백업(별도 호출), dry-run 지원, 표준 탐지 실패 시 보존,
원 라벨을 score_breakdown.category_recanonicalized_from 에 보존(되돌리기 가능).

사용:
  python scripts/recanonicalize_viral_categories.py --dry-run
  python scripts/recanonicalize_viral_categories.py            # 실제 적용(백업 먼저)
  python scripts/recanonicalize_viral_categories.py --statuses pending,generated,posted
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from typing import Callable, Iterable, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def canonical_categories() -> set:
    from core_services.gyulim_keyword_profile import GYULIM_KEYWORD_PROFILE
    canon = set(getattr(GYULIM_KEYWORD_PROFILE, "focus_categories", ()) or ())
    try:
        from core_services.viral_seed_builder import DEFAULT_CATEGORY_QUOTAS
        canon |= set(DEFAULT_CATEGORY_QUOTAS.keys())
    except Exception:
        pass
    canon |= {"경쟁사_역공략", "기타"}
    return canon


def _default_detector() -> Callable[[str], Optional[str]]:
    from core_services.gyulim_keyword_profile import GYULIM_KEYWORD_PROFILE
    return GYULIM_KEYWORD_PROFILE.detect_category


def recanonicalize_viral_categories(
    db_path: str,
    statuses: Iterable[str] = ("pending", "generated", "posted"),
    dry_run: bool = False,
    detector: Optional[Callable[[str], Optional[str]]] = None,
    canon: Optional[set] = None,
) -> dict:
    """비표준 category 행을 콘텐츠 재탐지로 표준 축으로 정정.

    - category 가 이미 표준이면 건드리지 않는다.
    - detect_category 가 표준 축을 못 내면 그대로 둔다(보존).
    - 경쟁사_역공략 은 진료축이 아니라 특수 레인이므로 절대 변경하지 않는다.
    """
    detector = detector or _default_detector()
    canon = canon if canon is not None else canonical_categories()
    status_list = [s for s in statuses if s]
    placeholders = ",".join(["?"] * len(status_list))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    stats = {"checked": 0, "relabeled": 0, "left_no_detect": 0, "transitions": Counter()}
    try:
        rows = conn.execute(
            f"""
            SELECT id, category, title, content_preview, score_breakdown
              FROM viral_targets
             WHERE comment_status IN ({placeholders})
            """,
            tuple(status_list),
        ).fetchall()
        for row in rows:
            current = (row["category"] or "").strip()
            # 표준 라벨이거나 특수 레인(경쟁사_역공략)이면 건너뛴다.
            if current in canon:
                continue
            stats["checked"] += 1
            text = ((row["title"] or "") + " " + (row["content_preview"] or "")).split("[기존답변", 1)[0]
            try:
                detected = detector(text)
            except Exception:
                detected = None
            if not detected or detected not in canon or detected == current:
                stats["left_no_detect"] += 1
                continue
            stats["relabeled"] += 1
            stats["transitions"][f"{current} -> {detected}"] += 1
            if dry_run:
                continue
            try:
                breakdown = json.loads(row["score_breakdown"] or "{}") or {}
            except (TypeError, ValueError):
                breakdown = {}
            breakdown.setdefault("category_recanonicalized_from", current)
            conn.execute(
                "UPDATE viral_targets SET category = ?, score_breakdown = ? WHERE id = ?",
                (detected, json.dumps(breakdown, ensure_ascii=False), row["id"]),
            )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    stats["transitions"] = dict(stats["transitions"].most_common())
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join("db", "marketing_data.db"))
    ap.add_argument("--statuses", default="pending,generated,posted")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]

    if not args.dry_run:
        import shutil
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{args.db}.backup_pre_recanon_{ts}"
        shutil.copyfile(args.db, backup)
        print(f"[backup] {backup}")

    stats = recanonicalize_viral_categories(args.db, statuses=statuses, dry_run=args.dry_run)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}checked(non-canonical)={stats['checked']} "
          f"relabeled={stats['relabeled']} left={stats['left_no_detect']}")
    for k, v in stats["transitions"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
