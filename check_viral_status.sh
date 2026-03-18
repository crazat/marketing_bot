#!/bin/bash
# Viral Hunter 완료 체크 스크립트

OUTPUT_FILE="/tmp/claude-1000/-mnt-c-Projects/tasks/b45ddc7.output"

if [ ! -f "$OUTPUT_FILE" ]; then
    echo "❌ 출력 파일을 찾을 수 없습니다."
    exit 1
fi

# 마지막 100줄 확인
LAST_LINES=$(tail -100 "$OUTPUT_FILE")

# 완료 여부 확인
if echo "$LAST_LINES" | grep -q "✅ 스캔 완료\|DB 저장 완료\|프로그램 종료"; then
    echo "✅ Viral Hunter 완료!"
    echo ""
    echo "=== 최종 결과 ==="
    tail -50 "$OUTPUT_FILE" | grep -A 20 "스캔 완료\|총 발견\|침투적합\|DB 저장"
    exit 0
else
    # 현재 진행 상황
    PROGRESS=$(echo "$LAST_LINES" | grep "진행:" | tail -1)
    CURRENT_KW=$(echo "$LAST_LINES" | grep "\[.*\].*검색 중" | tail -1)
    
    echo "🔄 진행 중..."
    if [ -n "$PROGRESS" ]; then
        echo "   $PROGRESS"
    fi
    if [ -n "$CURRENT_KW" ]; then
        echo "   $CURRENT_KW"
    fi
    exit 2
fi
