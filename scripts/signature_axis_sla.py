"""Lane E — 시그니처 축(흉터/안면비대칭) 발견 퍼널 SLA 리포트 (읽기 전용).

Lane A/B/C 가 실제로 바늘을 움직이는지 측정한다. 새 데이터를 쓰지 않고(read-only)
기존 테이블만 집계한다:
  · 골든큐 상태(viral_targets)            — raw_backlog 저수지 / pending / posted
  · 백로그 윈도우 갭(21일 vs 180일)        — Lane A 가 메우는 starvation 가시화
  · Q&A 지식 커버리지(qa_repository)        — Lane B 효과(축당 ≥1 목표)
  · 자체 콘텐츠 랭크(rank_history)          — Lane C 효과(발행 후 추적)
  · 발견 퍼널 트렌드(viral_scan_audits)     — 최근 스캔별 fresh/pending/ad/reject

실행: python scripts/signature_axis_sla.py [--audits 6] [--out reports/signature_axis_sla.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "db", "marketing_data.db")

SIGNATURE_AXES = ("흉터/여드름흉터", "안면비대칭")
# rank_history 매칭용 시그니처 콘텐츠 키워드 토큰(Lane C 발행 타겟).
RANK_TOKENS = ("새살침", "패인흉터", "여드름흉터", "안면비대칭", "얼굴비대칭", "턱비대칭")


def _q(c, sql, params=()):
    return c.execute(sql, params).fetchall()


def _golden_state(c):
    out = {}
    for ax in SIGNATURE_AXES:
        rows = _q(c, """
            SELECT COALESCE(comment_status,'?') s, COUNT(*) n
            FROM viral_targets WHERE matched_keyword_category=? GROUP BY s
        """, (ax,))
        out[ax] = {r[0]: r[1] for r in rows}
    return out


def _backlog_windows(c):
    out = {}
    for ax in SIGNATURE_AXES:
        win = {}
        for days in (21, 180):
            r = _q(c, """
                SELECT COUNT(*) FROM viral_targets
                WHERE COALESCE(comment_status,'pending') IN ('raw_backlog','needs_ai_retry')
                  AND COALESCE(is_commentable,1)=1
                  AND REPLACE(COALESCE(discovered_at,''),'T',' ') >= datetime('now', ?)
                  AND matched_keyword_category=?
            """, (f"-{days} days", ax))
            win[days] = r[0][0]
        out[ax] = win
    return out


def _qa_coverage(c):
    out = {}
    for ax in SIGNATURE_AXES:
        r = _q(c, "SELECT COUNT(*) FROM qa_repository WHERE question_category=?", (ax,))
        out[ax] = r[0][0]
    return out


def _owned_rank(c):
    cols = {r[1] for r in _q(c, "PRAGMA table_info(rank_history)")}
    ts = "checked_at" if "checked_at" in cols else ("scanned_date" if "scanned_date" in cols else None)
    rows = []
    like = " OR ".join("keyword LIKE ?" for _ in RANK_TOKENS)
    params = tuple(f"%{t}%" for t in RANK_TOKENS)
    if ts:
        sql = f"""
            SELECT keyword, rank, COALESCE(status,'?'), MAX({ts})
            FROM rank_history WHERE ({like})
            GROUP BY keyword ORDER BY {ts} DESC LIMIT 20
        """
    else:
        sql = f"SELECT keyword, rank, COALESCE(status,'?'), '' FROM rank_history WHERE ({like}) LIMIT 20"
    for r in _q(c, sql, params):
        rows.append({"keyword": r[0], "rank": r[1], "status": r[2], "at": r[3]})
    return rows


def _funnel_trend(c, n_audits):
    rows = _q(c, "SELECT id, run_started_at, audit_json FROM viral_scan_audits ORDER BY id DESC LIMIT ?", (n_audits,))
    trend = []
    for aid, started, aj in rows:
        try:
            pc = (json.loads(aj) if aj else {}).get("per_category", {})
        except Exception:
            pc = {}
        entry = {"audit_id": aid, "started": (started or "")[:16]}
        for ax in SIGNATURE_AXES:
            d = pc.get(ax, {}) or {}
            entry[ax] = {
                "fresh": d.get("fresh_discovered", 0),
                "fresh_pending": d.get("fresh_pending", 0),
                "pending": d.get("pending", 0),
                "open_pending": d.get("open_pending", 0),
                "raw_backlog": d.get("raw_backlog", 0),
                "ad": d.get("ad_filtered", 0),
                "rejected": d.get("rejected", 0),
            }
        trend.append(entry)
    return list(reversed(trend))  # 오래된→최신


def build_report(n_audits: int) -> str:
    conn = sqlite3.connect(_DB)
    try:
        c = conn.cursor()
        golden = _golden_state(c)
        backlog = _backlog_windows(c)
        qa = _qa_coverage(c)
        rank = _owned_rank(c)
        trend = _funnel_trend(c, n_audits)
    finally:
        conn.close()

    L = [f"# 시그니처 축 SLA 리포트", f"_생성: {datetime.now().isoformat(timespec='seconds')} · read-only_\n"]

    L.append("## 1. 골든큐 상태 (viral_targets)")
    for ax in SIGNATURE_AXES:
        g = golden.get(ax, {})
        L.append(f"- **{ax}**: pending {g.get('pending',0)} · raw_backlog {g.get('raw_backlog',0)} · "
                 f"posted {g.get('posted',0)} · generated {g.get('generated',0)} · skipped {g.get('skipped',0)}")

    L.append("\n## 2. 백로그 윈도우 갭 — Lane A 가 메우는 starvation")
    for ax in SIGNATURE_AXES:
        w = backlog.get(ax, {})
        gap = w.get(180, 0) - w.get(21, 0)
        L.append(f"- **{ax}**: 일반 레스큐(21일) {w.get(21,0)}건 → 시그니처 레인(180일) {w.get(180,0)}건 "
                 f"(**+{gap} 해금**)")

    L.append("\n## 3. Q&A 지식 커버리지 — Lane B (축당 ≥1 목표)")
    for ax in SIGNATURE_AXES:
        n = qa.get(ax, 0)
        L.append(f"- **{ax}**: {n}개 {'✅' if n >= 1 else '❌ 비어있음'}")

    L.append("\n## 4. 자체 콘텐츠 랭크 — Lane C (발행 후 추적)")
    if rank:
        for r in rank[:12]:
            L.append(f"- `{r['keyword']}`: rank {r['rank']} ({r['status']}) {r['at']}")
    else:
        L.append("- (아직 시그니처 콘텐츠 키워드 순위 데이터 없음 — 발행 + 순위 스캔 후 채워짐)")

    L.append("\n## 5. 발견 퍼널 트렌드 (최근 스캔)")
    for ax in SIGNATURE_AXES:
        L.append(f"\n**{ax}**  (fresh / fresh_pending / open_pending / actionable / ad_filtered / rejected)")
        for e in trend:
            d = e[ax]
            L.append(f"- #{e['audit_id']} {e['started']}: fresh {d['fresh']} · fresh_pending {d['fresh_pending']} · "
                     f"open {d['open_pending']} · actionable {d['pending']} · ad {d['ad']} · reject {d['rejected']}")

    # SLA 판정
    L.append("\n## 6. SLA 판정")
    for ax in SIGNATURE_AXES:
        qa_ok = qa.get(ax, 0) >= 1
        backlog_supply = backlog.get(ax, {}).get(180, 0)
        verdict = []
        verdict.append(f"Q&A {'OK' if qa_ok else 'GAP'}")
        verdict.append(f"백로그공급 {backlog_supply}")
        if len(trend) >= 2:
            d0, d1 = trend[0][ax]["pending"], trend[-1][ax]["pending"]
            arrow = "↑" if d1 > d0 else ("↓" if d1 < d0 else "→")
            verdict.append(f"pending {d0}{arrow}{d1}")
        L.append(f"- **{ax}**: " + " · ".join(verdict))

    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="시그니처 축 SLA 리포트 (Lane E)")
    ap.add_argument("--audits", type=int, default=6, help="트렌드에 포함할 최근 audit 수")
    ap.add_argument("--out", default=os.path.join(_ROOT, "reports", "signature_axis_sla.md"))
    args = ap.parse_args()

    report = build_report(args.audits)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(report)
    print(report)
    print(f"\n📁 저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
