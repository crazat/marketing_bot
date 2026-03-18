"""노이즈 데이터 정리 스크립트"""
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('db/marketing_data.db')
cursor = conn.cursor()

# 모든 YouTube 리드 삭제 (새로 시작)
cursor.execute("DELETE FROM mentions WHERE source='youtube_comment'")
deleted = cursor.rowcount
conn.commit()

print(f'삭제된 YouTube 리드: {deleted}건')
print('이제 새로 스캔하면 개선된 분류기로 수집됩니다.')

conn.close()
