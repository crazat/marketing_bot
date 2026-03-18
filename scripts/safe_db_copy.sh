#!/bin/bash
# 안전한 DB 복사 스크립트
# 덮어쓰기 전 경고 및 백업 자동 생성

set -e

SOURCE="$1"
DEST="$2"

if [ -z "$SOURCE" ] || [ -z "$DEST" ]; then
    echo "사용법: ./safe_db_copy.sh <원본DB> <대상DB>"
    echo "예시: ./safe_db_copy.sh /home/crazat/db.db /mnt/c/projects/db.db"
    exit 1
fi

if [ ! -f "$SOURCE" ]; then
    echo "❌ 원본 파일이 존재하지 않습니다: $SOURCE"
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              ⚠️  DB 복사 안전 확인 ⚠️                       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 원본 정보
echo "📤 원본: $SOURCE"
echo "   크기: $(du -h "$SOURCE" | cut -f1)"
if command -v sqlite3 &> /dev/null; then
    SRC_COUNT=$(sqlite3 "$SOURCE" "SELECT COUNT(*) FROM viral_targets" 2>/dev/null || echo "N/A")
    echo "   viral_targets: ${SRC_COUNT}개"
fi

echo ""

# 대상 정보
if [ -f "$DEST" ]; then
    echo "📥 대상 (기존 파일 존재): $DEST"
    echo "   크기: $(du -h "$DEST" | cut -f1)"
    if command -v sqlite3 &> /dev/null; then
        DEST_COUNT=$(sqlite3 "$DEST" "SELECT COUNT(*) FROM viral_targets" 2>/dev/null || echo "N/A")
        echo "   viral_targets: ${DEST_COUNT}개"
    fi
    
    echo ""
    echo "⚠️  경고: 대상 파일이 이미 존재합니다!"
    echo "   복사하면 기존 데이터가 삭제됩니다."
    echo ""
    
    # 대상이 더 많은 데이터를 가지고 있으면 강력 경고
    if [ "$DEST_COUNT" != "N/A" ] && [ "$SRC_COUNT" != "N/A" ]; then
        if [ "$DEST_COUNT" -gt "$SRC_COUNT" ]; then
            echo "🚨🚨🚨 심각한 경고 🚨🚨🚨"
            echo "   대상 DB(${DEST_COUNT}개)가 원본(${SRC_COUNT}개)보다 더 많은 데이터를 가지고 있습니다!"
            echo "   이 작업은 데이터 손실을 초래할 수 있습니다!"
            echo ""
        fi
    fi
    
    read -p "정말 계속하시겠습니까? (yes 입력): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "❌ 취소됨"
        exit 1
    fi
    
    # 자동 백업 생성
    echo ""
    echo "📦 대상 DB 백업 생성 중..."
    BACKUP_PATH="${DEST}.backup_before_copy_$(date +%Y%m%d_%H%M%S)"
    cp "$DEST" "$BACKUP_PATH"
    echo "✅ 백업 생성: $BACKUP_PATH"
else
    echo "📥 대상 (새 파일): $DEST"
fi

echo ""
echo "🔄 복사 실행 중..."
cp "$SOURCE" "$DEST"

echo ""
echo "✅ 복사 완료!"
echo "   대상: $DEST"
echo "   크기: $(du -h "$DEST" | cut -f1)"
