"""Curated 시드 list로 viral_hunter 실행 (option C: run5 S+A + 누적 KEI>=500 S)."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viral_hunter import ViralHunter

with open('logs/viral_seeds_curated.json', encoding='utf-8') as f:
    keywords = json.load(f)

print(f'=== Curated viral hunter — 시드 {len(keywords)}개 ===')
for k in keywords:
    print(f'  - {k}')
print()

hunter = ViralHunter()
hunter.hunt(keywords=keywords, fresh=True, checkpoint_every=5,
            top_n_for_ai=500, ai_parallel=5)
