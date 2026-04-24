"""
Viral Hunter 키워드 로딩 개선 버전
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

개선 사항:
1. 키워드 변경 추적 (추가/제거 로깅)
2. Pathfinder 업데이트 시간 기록
3. 키워드 변경 히스토리
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Set

class KeywordChangeTracker:
    """키워드 변경 추적 클래스"""

    def __init__(self, history_file='logs/keyword_changes.json'):
        self.history_file = history_file
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """로그 디렉토리 생성"""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_previous_keywords(self) -> Set[str]:
        """이전 키워드 세트 로드"""
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                if history:
                    return set(history[-1].get('keywords', []))
        except Exception:
            pass
        return set()

    def track_changes(self, previous: Set[str], current: Set[str]) -> Dict:
        """키워드 변경 추적"""
        added = current - previous
        removed = previous - current
        unchanged = previous & current

        change_log = {
            'timestamp': datetime.now().isoformat(),
            'keywords': list(current),
            'total': len(current),
            'changes': {
                'added': list(added),
                'removed': list(removed),
                'added_count': len(added),
                'removed_count': len(removed),
                'unchanged_count': len(unchanged)
            }
        }

        # 히스토리 저장
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []

        history.append(change_log)

        # 최근 30일만 유지
        if len(history) > 30:
            history = history[-30:]

        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        return change_log

    def log_changes(self, change_log: Dict):
        """변경 사항 로깅"""
        changes = change_log['changes']

        if changes['added_count'] > 0:
            print(f"\n✨ 새로 추가된 키워드: {changes['added_count']}개")
            for kw in changes['added'][:10]:  # 상위 10개만
                print(f"   + {kw}")
            if changes['added_count'] > 10:
                print(f"   ... (외 {changes['added_count'] - 10}개)")

        if changes['removed_count'] > 0:
            print(f"\n🗑️ 제거된 키워드: {changes['removed_count']}개")
            for kw in changes['removed'][:10]:
                print(f"   - {kw}")
            if changes['removed_count'] > 10:
                print(f"   ... (외 {changes['removed_count'] - 10}개)")

        if changes['added_count'] == 0 and changes['removed_count'] == 0:
            print("\n✅ 키워드 변경 없음")


# === 사용 예시 ===

def enhanced_load_keywords_example():
    """
    viral_hunter.py의 _load_keywords() 함수에 추가할 코드
    """

    # 기존 키워드 로딩 로직
    keywords = set()
    # ... (targets.json, campaigns.json, Pathfinder 로딩) ...

    # === 추가: 변경 추적 ===
    tracker = KeywordChangeTracker()
    previous_keywords = tracker.load_previous_keywords()
    current_keywords = keywords

    # 변경 사항 추적
    change_log = tracker.track_changes(previous_keywords, current_keywords)

    # 변경 사항 로깅
    tracker.log_changes(change_log)

    return list(keywords)


if __name__ == "__main__":
    print("="*70)
    print("🧪 키워드 변경 추적 시스템 데모")
    print("="*70)
    print()

    # 시뮬레이션
    tracker = KeywordChangeTracker('logs/keyword_changes_test.json')

    # 1차 실행 (초기 키워드)
    print("📊 1차 실행 (2월 1일)")
    print("-"*70)
    keywords_feb1 = {'청주 다이어트', '청주 교통사고', '청주 한의원'}
    prev = tracker.load_previous_keywords()
    log1 = tracker.track_changes(prev, keywords_feb1)
    tracker.log_changes(log1)

    print()

    # 2차 실행 (Pathfinder 업데이트 후)
    print("📊 2차 실행 (2월 6일 - Pathfinder 실행 후)")
    print("-"*70)
    keywords_feb6 = keywords_feb1 | {'세종 목디스크', '청주 공황장애', '증평 한의원'}
    keywords_feb6.remove('청주 한의원')  # 등급 하락으로 제거

    prev = tracker.load_previous_keywords()
    log2 = tracker.track_changes(prev, keywords_feb6)
    tracker.log_changes(log2)

    print()
    print("="*70)
    print("✅ 데모 완료!")
    print("="*70)
    print()
    print(f"변경 히스토리: {tracker.history_file}")
