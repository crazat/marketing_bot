"""Viral Hunter Daily Brief — 오전 09:00 실행 (cron 또는 Chronos Timeline에 등록).

어제 발굴된 HOT LEAD를 Tier별로 묶어 하루 1회 요약 Telegram 발송.
- Tier 2 (점수 100~119): 카테고리별 상위 N건
- Tier 3 (점수 80~99): 건수 요약만

매 스캔마다 폭주하던 Telegram 알림을 하루 1회로 집약.
"""
from __future__ import annotations

import os
import sys
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DB_PATH = os.path.join(ROOT, "db", "marketing_data.db")


def build_brief() -> str:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 지난 24시간 내 발견된 타겟 기준
    cur.execute(
        """
        SELECT priority_score, platform, category, title, url, matched_keyword
        FROM viral_targets
        WHERE discovered_at >= datetime('now', '-1 day')
          AND priority_score >= 80
        ORDER BY priority_score DESC
        """
    )
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return ""

    tier2 = [r for r in rows if 100 <= (r["priority_score"] or 0) < 120]
    tier3 = [r for r in rows if 80 <= (r["priority_score"] or 0) < 100]

    today = datetime.now().strftime("%Y-%m-%d")
    msg = [f"📰 **Viral Hunter Daily Brief** · {today}"]
    msg.append(f"지난 24시간 신규 HOT LEAD: **{len(rows):,}건**\n")

    # Tier 2: 카테고리별 상위 3건 × 최대 5 카테고리
    if tier2:
        msg.append(f"🟠 **Tier 2** (점수 100~119, {len(tier2):,}건)")
        by_category: dict = {}
        for r in tier2:
            by_category.setdefault(r["category"] or "기타", []).append(r)
        for i, (cat, items) in enumerate(sorted(by_category.items(), key=lambda x: -len(x[1]))[:5], 1):
            msg.append(f"\n· **{cat}** ({len(items)}건)")
            for r in items[:3]:
                pf_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(r["platform"], "📌")
                msg.append(f"  {pf_icon} {r['title'][:60]}\n    {r['url']}")

    # Tier 3: 카테고리별 건수 요약만
    if tier3:
        by_cat = {}
        for r in tier3:
            by_cat[r["category"] or "기타"] = by_cat.get(r["category"] or "기타", 0) + 1
        summary = " / ".join(f"{k} {v}건" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])[:10])
        msg.append(f"\n🟡 **Tier 3** (점수 80~99, {len(tier3):,}건): {summary}")

    msg.append("\n상세는 Viral Hunter 대시보드에서 확인하세요.")
    conn.close()
    return "\n".join(msg)


def main() -> None:
    brief = build_brief()
    if not brief:
        print("Daily Brief: 최근 24시간 HOT LEAD 없음 — 발송 스킵")
        return

    try:
        from alert_bot import TelegramBot
        bot = TelegramBot()
        bot.send_message(brief)
        print("✅ Daily Brief 발송 완료")
    except Exception as e:
        print(f"❌ Daily Brief 발송 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
