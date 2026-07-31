"""scripts/recanonicalize_viral_categories.py 의 핵심 로직 회귀 테스트.

레거시/비표준 category 행만 콘텐츠 재탐지로 표준 축으로 정정하고, 표준 라벨·특수
레인(경쟁사_역공략)은 보존하며, 탐지 실패 시 원본을 남기고, 원 라벨 lineage를 보존한다.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recanonicalize_viral_categories import recanonicalize_viral_categories  # noqa: E402

CANON = {"피부/여드름", "흉터/여드름흉터", "체형교정", "안면비대칭", "경쟁사_역공략", "기타"}


def _detector(text: str):
    # 콘텐츠 기반 결정적 가짜 탐지기
    if "흉터" in text or "새살침" in text:
        return "흉터/여드름흉터"
    if "골반" in text or "체형" in text:
        return "체형교정"
    if "여드름" in text or "피부" in text:
        return "피부/여드름"
    if "삐뚤" in text or "비대칭" in text:
        return "안면비대칭"
    return None


def _make_db(tmp_path, rows):
    db = tmp_path / "recanon.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE viral_targets (
        id TEXT PRIMARY KEY, category TEXT, comment_status TEXT,
        title TEXT, content_preview TEXT, score_breakdown TEXT)""")
    conn.executemany(
        "INSERT INTO viral_targets VALUES (?,?,?,?,?,?)", rows
    )
    conn.commit(); conn.close()
    return str(db)


def test_recanonicalize_relabels_legacy_only(tmp_path):
    rows = [
        # 레거시 '피부' 인데 실제 SCAR → 흉터/여드름흉터 로 정정(시그니처 축 surfacing)
        ("a", "피부", "pending", "여드름흉터 볼 치료", "패인 여드름흉터 새살침 고민", "{}"),
        # 레거시 '비대칭/교정' 인데 실제 체형교정 → 체형교정 (블라인드 안면비대칭 매핑 방지)
        ("b", "비대칭/교정", "pending", "골반 틀어짐 교정", "골반 체형교정 문의", "{}"),
        # 이미 표준 라벨 → 절대 변경 안 함
        ("c", "피부/여드름", "pending", "여드름 치료", "여드름 피부 상담", "{}"),
        # 특수 레인(경쟁사_역공략, 표준 취급) → 변경 안 함
        ("d", "경쟁사_역공략", "pending", "여드름흉터 어디 좋아요", "흉터 새살침", "{}"),
        # 탐지 불가 → 원본 보존
        ("e", "기타증상", "pending", "그냥 질문", "내용 없음", "{}"),
        # 비대상 상태(filtered) → 건드리지 않음
        ("f", "피부", "filtered_out", "여드름흉터", "흉터", "{}"),
    ]
    db = _make_db(tmp_path, rows)
    stats = recanonicalize_viral_categories(
        db, statuses=("pending", "generated", "posted"),
        dry_run=False, detector=_detector, canon=CANON,
    )
    assert stats["relabeled"] == 2
    conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
    got = {r["id"]: (r["category"], r["score_breakdown"]) for r in conn.execute("SELECT id, category, score_breakdown FROM viral_targets")}
    conn.close()
    assert got["a"][0] == "흉터/여드름흉터"                      # 숨은 SCAR 정정
    assert json.loads(got["a"][1]).get("category_recanonicalized_from") == "피부"  # lineage 보존
    assert got["b"][0] == "체형교정"                            # 비대칭/교정 → 체형교정(정확)
    assert got["c"][0] == "피부/여드름"                          # 표준 라벨 불변
    assert got["d"][0] == "경쟁사_역공략"                        # 특수 레인 불변
    assert got["e"][0] == "기타증상"                            # 탐지 실패 보존
    assert got["f"][0] == "피부"                                # 비대상 상태 불변


def test_recanonicalize_dry_run_no_write(tmp_path):
    rows = [("a", "피부", "pending", "여드름흉터", "흉터 새살침", "{}")]
    db = _make_db(tmp_path, rows)
    stats = recanonicalize_viral_categories(
        db, dry_run=True, detector=_detector, canon=CANON
    )
    assert stats["relabeled"] == 1
    conn = sqlite3.connect(db)
    cat = conn.execute("SELECT category FROM viral_targets WHERE id='a'").fetchone()[0]
    conn.close()
    assert cat == "피부"   # dry-run 은 DB 변경 없음
