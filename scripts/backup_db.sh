#!/bin/bash
# DB 백업 스크립트
# 사용법: ./backup_db.sh [설명]

set -e

DB_PATH="/mnt/c/projects/marketing_bot/db/marketing_data.db"
BACKUP_DIR="/mnt/c/projects/marketing_bot/db/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DESCRIPTION="${1:-manual}"

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# 백업 파일명
BACKUP_FILE="$BACKUP_DIR/marketing_data.db.backup_${TIMESTAMP}_${DESCRIPTION}"

# DB 존재 확인
if [ ! -f "$DB_PATH" ]; then
    echo "❌ 오류: DB 파일을 찾을 수 없습니다: $DB_PATH"
    exit 1
fi

# 백업 전 DB 정보 출력
echo "📊 백업 전 DB 상태:"
echo "   파일 크기: $(du -h "$DB_PATH" | cut -f1)"
if command -v sqlite3 &> /dev/null; then
    VIRAL_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM viral_targets" 2>/dev/null || echo "N/A")
    echo "   viral_targets: ${VIRAL_COUNT}개"
fi

# 백업 실행
cp "$DB_PATH" "$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ]; then
    echo ""
    echo "✅ 백업 완료: $BACKUP_FILE"
    echo "   백업 크기: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    echo "❌ 백업 실패"
    exit 1
fi

# 오래된 백업 정리 (30개 초과 시)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/marketing_data.db.backup_* 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 30 ]; then
    echo ""
    echo "🧹 오래된 백업 정리 중... (현재 ${BACKUP_COUNT}개, 30개 유지)"
    ls -1t "$BACKUP_DIR"/marketing_data.db.backup_* | tail -n +31 | xargs rm -f
    echo "   정리 완료"
fi

echo ""
echo "📁 현재 백업 목록:"
ls -lht "$BACKUP_DIR"/marketing_data.db.backup_* 2>/dev/null | head -5
