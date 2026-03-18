#!/usr/bin/env python3
"""
키워드 신규성 및 다양성 분석
- 이전 실행 대비 완전 신규 키워드 비율
- 유사 키워드 클러스터 분석
- 발굴 잠재력 평가
"""
import sqlite3
from collections import defaultdict, Counter
from datetime import datetime
import re

DB_PATH = "/mnt/c/Projects/marketing_bot/db/marketing_data.db"

def get_core_words(keyword):
    """키워드에서 핵심 단어 추출 (공백/조사 제거)"""
    # 지역명 제거
    keyword = re.sub(r'^(청주|충주|증평|진천|괴산|음성|단양)', '', keyword)
    # 공백 제거
    keyword = keyword.replace(' ', '')
    # 2글자 이상 단어만 추출
    words = re.findall(r'[가-힣]{2,}', keyword)
    return set(words)

def analyze_novelty():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 날짜별 키워드 가져오기
    cursor.execute("""
        SELECT DATE(created_at) as date, keyword, grade
        FROM keyword_insights
        WHERE DATE(created_at) >= DATE('now', '-7 days')
        ORDER BY created_at
    """)
    
    results = cursor.fetchall()
    
    # 날짜별로 분류
    by_date = defaultdict(list)
    for date, keyword, grade in results:
        by_date[date].append((keyword, grade))
    
    dates = sorted(by_date.keys())
    
    print("=" * 70)
    print("🔍 Pathfinder 신규성 분석 - 이전 실행 대비 새로운 키워드 발굴")
    print("=" * 70)
    print()
    
    # 이전 모든 키워드들의 핵심 단어 수집
    prev_keywords = set()
    prev_core_words = set()
    
    for i, date in enumerate(dates):
        keywords_today = [kw for kw, _ in by_date[date]]
        grades_today = [gr for _, gr in by_date[date]]
        
        print(f"📅 {date} 실행 결과")
        print(f"   총 키워드: {len(keywords_today)}개")
        print(f"   등급 분포: S={grades_today.count('S')}, A={grades_today.count('A')}, B={grades_today.count('B')}, C={grades_today.count('C')}")
        
        if i > 0:  # 이전 실행이 있는 경우
            # 1. 완전 일치 중복 (동일 키워드)
            exact_duplicates = [kw for kw in keywords_today if kw in prev_keywords]
            exact_new = len(keywords_today) - len(exact_duplicates)
            
            # 2. 핵심 단어 기반 유사도 (새로운 조합인지)
            core_novel = 0
            core_similar = 0
            
            for keyword in keywords_today:
                core_words = get_core_words(keyword)
                if core_words and not core_words.issubset(prev_core_words):
                    core_novel += 1
                elif core_words:
                    core_similar += 1
            
            print(f"\n   📊 이전 실행 대비:")
            print(f"      • 완전 동일: {len(exact_duplicates)}개 ({len(exact_duplicates)/len(keywords_today)*100:.1f}%)")
            print(f"      • 완전 신규: {exact_new}개 ({exact_new/len(keywords_today)*100:.1f}%)")
            print(f"      • 새로운 단어 조합: {core_novel}개 ({core_novel/len(keywords_today)*100:.1f}%)")
            print(f"      • 기존 단어 재조합: {core_similar}개 ({core_similar/len(keywords_today)*100:.1f}%)")
            
            # 신규 핵심 단어 발굴
            new_words = set()
            for keyword in keywords_today:
                new_words.update(get_core_words(keyword) - prev_core_words)
            
            if new_words:
                print(f"      • 신규 발굴 단어: {len(new_words)}개")
                if len(new_words) <= 10:
                    print(f"        → {', '.join(sorted(new_words)[:10])}")
        
        # 현재 날짜의 키워드를 누적
        prev_keywords.update(keywords_today)
        for keyword in keywords_today:
            prev_core_words.update(get_core_words(keyword))
        
        print()
    
    # 전체 통계
    print("=" * 70)
    print("📈 발굴 잠재력 평가")
    print("=" * 70)
    
    total_keywords = len(prev_keywords)
    total_core_words = len(prev_core_words)
    
    print(f"• 전체 발굴 키워드: {total_keywords}개")
    print(f"• 고유 핵심 단어: {total_core_words}개")
    print(f"• 평균 키워드 길이: {sum(len(kw) for kw in prev_keywords) / len(prev_keywords):.1f}자")
    
    # 가장 많이 사용된 단어들
    word_counter = Counter()
    for keyword in prev_keywords:
        word_counter.update(get_core_words(keyword))
    
    print(f"\n🔥 가장 많이 사용된 핵심 단어 TOP 10:")
    for word, count in word_counter.most_common(10):
        print(f"   {word}: {count}회 ({count/total_keywords*100:.1f}%)")
    
    # 발굴 잠재력 점수
    avg_new_ratio = 90.0  # 기본값 (첫 실행은 100%)
    if len(dates) > 1:
        # 마지막 실행의 신규 비율
        last_date = dates[-1]
        keywords_last = [kw for kw, _ in by_date[last_date]]
        prev_all = set()
        for d in dates[:-1]:
            prev_all.update([kw for kw, _ in by_date[d]])
        
        exact_new_last = sum(1 for kw in keywords_last if kw not in prev_all)
        avg_new_ratio = exact_new_last / len(keywords_last) * 100
    
    print(f"\n💎 발굴 잠재력 점수:")
    if avg_new_ratio >= 95:
        score = "A+ (매우 우수)"
        comment = "매 실행마다 거의 모든 키워드가 신규입니다. 발굴 전략이 매우 효과적입니다."
    elif avg_new_ratio >= 80:
        score = "A (우수)"
        comment = "대부분 새로운 키워드를 발굴하고 있습니다. 지속 가능한 수준입니다."
    elif avg_new_ratio >= 60:
        score = "B (양호)"
        comment = "새로운 키워드를 발굴하고 있지만, 중복이 증가하는 추세입니다."
    else:
        score = "C (개선 필요)"
        comment = "중복 키워드가 많습니다. 새로운 발굴 전략이 필요합니다."
    
    print(f"   점수: {score}")
    print(f"   신규율: {avg_new_ratio:.1f}%")
    print(f"   평가: {comment}")
    
    conn.close()

if __name__ == "__main__":
    analyze_novelty()
