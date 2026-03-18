import sqlite3

conn = sqlite3.connect('db/marketing_data.db')
cursor = conn.cursor()

print('=' * 80)
print('KEI 500+ Golden Keywords')
print('=' * 80)
cursor.execute('''
    SELECT keyword, search_volume, volume, opp_score, category
    FROM keyword_insights
    WHERE opp_score >= 500
    ORDER BY opp_score DESC
''')
golden = cursor.fetchall()
if golden:
    for row in golden:
        kw, vol, supply, kei, cat = row
        print(f'{kw} | Vol: {vol:,} | Supply: {supply:,} | KEI: {kei:.0f} | {cat}')
else:
    print('No KEI 500+ keywords found')

print('\n' + '=' * 80)
print('상위 20개 키워드 (KEI 높은 순)')
print('=' * 80)
cursor.execute('''
    SELECT keyword, search_volume, volume, opp_score, category
    FROM keyword_insights
    ORDER BY opp_score DESC
    LIMIT 20
''')
for i, row in enumerate(cursor.fetchall(), 1):
    kw, vol, supply, kei, cat = row
    print(f'{i:2d}. {kw:40s} | Vol: {vol:5,} | Supply: {supply:6,} | KEI: {kei:5.0f} | {cat}')

print('\n' + '=' * 80)
print('하위 20개 키워드 (KEI 낮은 순)')
print('=' * 80)
cursor.execute('''
    SELECT keyword, search_volume, volume, opp_score, category
    FROM keyword_insights
    ORDER BY opp_score ASC
    LIMIT 20
''')
for i, row in enumerate(cursor.fetchall(), 1):
    kw, vol, supply, kei, cat = row
    print(f'{i:2d}. {kw:40s} | Vol: {vol:5,} | Supply: {supply:6,} | KEI: {kei:5.0f} | {cat}')

conn.close()
