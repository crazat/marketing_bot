#!/bin/bash
# Viral Hunter 완료 대기 스크립트 (최대 12시간)

OUTPUT_FILE="/tmp/claude-1000/-mnt-c-Projects/tasks/b45ddc7.output"
MAX_WAIT_HOURS=12
CHECK_INTERVAL=600  # 10분마다 체크

echo "🔄 Viral Hunter 완료 대기 중..."
echo "   최대 대기 시간: ${MAX_WAIT_HOURS}시간"
echo "   체크 주기: $((CHECK_INTERVAL / 60))분"
echo ""

start_time=$(date +%s)
max_wait_seconds=$((MAX_WAIT_HOURS * 3600))

while true; do
    elapsed=$(($(date +%s) - start_time))
    
    if [ $elapsed -ge $max_wait_seconds ]; then
        echo "⏰ 최대 대기 시간 초과"
        break
    fi
    
    # 완료 여부 확인
    if grep -q "✅ 스캔 완료\|DB 저장 완료" "$OUTPUT_FILE" 2>/dev/null; then
        echo ""
        echo "✅✅✅ Viral Hunter 완료! ✅✅✅"
        echo ""
        bash /mnt/c/Projects/marketing_bot/check_viral_status.sh
        exit 0
    fi
    
    # 진행 상황 출력
    progress=$(tail -100 "$OUTPUT_FILE" 2>/dev/null | grep "진행:" | tail -1)
    elapsed_hours=$((elapsed / 3600))
    elapsed_mins=$(((elapsed % 3600) / 60))
    
    echo "[$(date '+%H:%M:%S')] 경과: ${elapsed_hours}h ${elapsed_mins}m | $progress"
    
    sleep $CHECK_INTERVAL
done

echo "⚠️ 완료를 확인하지 못했습니다. 수동으로 확인해주세요."
exit 1
