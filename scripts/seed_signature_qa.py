"""Lane B — 시그니처 Q&A 드래프트를 qa_repository 에 적재하는 마이그레이션 스크립트.

``scripts/generate_signature_qa_drafts.py`` 가 만든 ``reports/signature_qa_drafts.json``
을 사람이 검수한 뒤 이 스크립트로만 적재한다(DML = 마이그레이션 스크립트로만 원칙).

안전장치:
- 기본 **dry-run** — ``--apply`` 없으면 무엇이 적재될지 출력만 한다.
- ``--apply`` 시 적재 전 SQLite Backup API 로 db/backups/ 에 백업 생성.
- **멱등**: 동일 question_pattern 이 이미 있으면 건너뛴다(재실행 안전).

실행:
  python scripts/seed_signature_qa.py            # dry-run(미리보기)
  python scripts/seed_signature_qa.py --apply    # 백업 후 실제 적재
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "db", "marketing_data.db")
_DRAFTS = os.path.join(_ROOT, "reports", "signature_qa_drafts.json")
_BACKUP_DIR = os.path.join(_ROOT, "db", "backups")


def _backup_db() -> str:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_path = os.path.join(_BACKUP_DIR, f"marketing_data.db.backup_{ts}")
    src = sqlite3.connect(_DB)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)  # SQLite Backup API (권장)
        finally:
            dst.close()
    finally:
        src.close()
    return dst_path


def main() -> int:
    ap = argparse.ArgumentParser(description="시그니처 Q&A 적재 (Lane B)")
    ap.add_argument("--apply", action="store_true", help="실제 적재(미지정 시 dry-run)")
    ap.add_argument("--drafts", default=_DRAFTS)
    args = ap.parse_args()

    if not os.path.exists(args.drafts):
        print(f"❌ 드래프트 파일 없음: {args.drafts}\n   먼저 generate_signature_qa_drafts.py 실행")
        return 1

    payload = json.load(open(args.drafts, encoding="utf-8"))
    drafts = payload.get("drafts") or []
    if not drafts:
        print("❌ 드래프트가 비어 있습니다.")
        return 1

    conn = sqlite3.connect(_DB)
    try:
        conn.row_factory = sqlite3.Row
        existing = {
            r["question_pattern"]
            for r in conn.execute("SELECT question_pattern FROM qa_repository").fetchall()
        }
        to_insert = [d for d in drafts if d.get("question_pattern") not in existing]
        skipped = len(drafts) - len(to_insert)

        print(f"📋 드래프트 {len(drafts)}개 | 신규 {len(to_insert)} | 중복 skip {skipped}")
        for d in to_insert:
            print(f"   + [{d.get('question_category')}] {d.get('question_pattern', '')[:50]}")

        if not args.apply:
            print("\n🔍 DRY-RUN — 적재 안 함. 실제 적재: --apply")
            return 0

        if not to_insert:
            print("✅ 신규 항목 없음(이미 전부 적재됨). 변경 없음.")
            return 0

        bak = _backup_db()
        print(f"💾 백업 생성: {bak}")

        now = datetime.now().isoformat(timespec="seconds")
        inserted = 0
        for d in to_insert:
            conn.execute(
                """
                INSERT INTO qa_repository
                    (question_pattern, question_category, standard_answer,
                     variations, use_count, created_at, updated_at, search_intent)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    d.get("question_pattern", ""),
                    d.get("question_category", ""),
                    d.get("standard_answer", ""),
                    json.dumps(d.get("variations") or [], ensure_ascii=False),
                    now,
                    now,
                    d.get("search_intent", "treatment_inquiry"),
                ),
            )
            inserted += 1
        conn.commit()
        print(f"✅ qa_repository 적재 완료: {inserted}개 (시그니처 축)")
        print("   ⚠️ 댓글 드래프터 RAG 인덱스 재빌드가 필요할 수 있음(BGE-M3 embed).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
