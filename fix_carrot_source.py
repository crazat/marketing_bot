import sqlite3

conn = sqlite3.connect('db/marketing_data.db')
c = conn.cursor()

print("=== 기존 당근마켓 리드 수정 ===")

# 당근마켓 리드 확인
c.execute("SELECT COUNT(*) FROM mentions WHERE source = '당근마켓'")
count = c.fetchone()[0]
print(f"수정할 리드: {count}개")

# source를 'carrot'로 변경
c.execute("UPDATE mentions SET source = 'carrot' WHERE source = '당근마켓'")
conn.commit()

print(f"✅ {c.rowcount}개 리드 수정 완료")

# 확인
c.execute("SELECT COUNT(*) FROM mentions WHERE source LIKE 'carrot%'")
total = c.fetchone()[0]
print(f"\n현재 당근마켓 리드: {total}개")

c.execute("SELECT id, source, title FROM mentions WHERE source LIKE 'carrot%' ORDER BY id DESC LIMIT 5")
print("\n최근 5개:")
for row in c.fetchall():
    print(f"  ID {row[0]}: source={row[1]} - {row[2][:50]}...")

conn.close()
print("\n✅ 완료! 이제 웹 UI에서 새로고침하면 보입니다.")
