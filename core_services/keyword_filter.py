#!/usr/bin/env python3
"""
Pathfinder V3 키워드 품질 필터
- 노이즈 키워드 제거
- 블랙리스트 필터링
- 관련성 점수 계산
"""

import re
import json
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FilterResult:
    """필터링 결과"""
    is_valid: bool
    reason: str
    relevance_score: float = 0.0  # 0.0 ~ 1.0


class KeywordQualityFilter:
    """키워드 품질 필터 파이프라인"""

    def __init__(self, config_path: str = None):
        # 기본 설정
        self.min_length = 2
        self.max_length = 70  # 개선: 50→70 (롱테일 키워드 허용)

        # 특수문자 패턴
        self.special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '~', '`']

        # 스팸 패턴
        self.spam_patterns = [
            r'ㅋ{2,}',  # ㅋㅋㅋ
            r'ㅎ{2,}',  # ㅎㅎㅎ
            r'[0-9]{5,}',  # 연속 숫자 5개 이상
            r'(.)\1{3,}',  # 같은 문자 4번 이상 반복
        ]

        # 핵심 비즈니스 키워드 (관련성 점수용)
        self.core_keywords = {
            'tier1': ['한의원', '한방', '한약', '침', '추나', '부항', '뜸'],
            'tier2': [
                '다이어트', '비만', '교통사고', '자동차사고', '입원',
                '안면비대칭', '비대칭', '여드름', '여드름흉터', '흉터',
                '새살침', '패인흉터', '모공흉터', '리프팅', '매선'
            ],
            'tier3': ['청주', '충북', '세종', '오창', '오송'],
        }

        # 블랙리스트 로드
        self.blacklist: Set[str] = set()
        self._load_blacklist(config_path)

    def _load_blacklist(self, config_path: str = None):
        """블랙리스트 로드"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'blacklist.json'

        try:
            if Path(config_path).exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.blacklist = set(data.get('keywords', []))
                    # 경쟁사명도 블랙리스트에 추가
                    self.blacklist.update(data.get('competitors', []))
        except Exception as e:
            print(f"⚠️ 블랙리스트 로드 실패: {e}")

    def validate(self, keyword: str) -> FilterResult:
        """
        키워드 검증

        Returns:
            FilterResult(is_valid, reason, relevance_score)
        """
        # 1. 길이 검증
        if len(keyword) < self.min_length:
            return FilterResult(False, 'too_short', 0.0)
        if len(keyword) > self.max_length:
            return FilterResult(False, 'too_long', 0.0)

        # 2. 특수문자 검증
        if any(c in keyword for c in self.special_chars):
            return FilterResult(False, 'special_char', 0.0)

        # 3. 스팸 패턴 검증
        for pattern in self.spam_patterns:
            if re.search(pattern, keyword):
                return FilterResult(False, 'spam_pattern', 0.0)

        # 4. 블랙리스트 체크
        keyword_lower = keyword.lower()
        for blocked in self.blacklist:
            if blocked.lower() in keyword_lower:
                return FilterResult(False, f'blacklisted:{blocked}', 0.0)

        # 5. 관련성 점수 계산
        relevance = self._calculate_relevance(keyword)

        return FilterResult(True, 'passed', relevance)

    def _calculate_relevance(self, keyword: str) -> float:
        """관련성 점수 계산 (0.0 ~ 1.0)"""
        score = 0.0
        keyword_lower = keyword.lower()

        # Tier 1: 핵심 한방 키워드 (0.4)
        if any(term in keyword_lower for term in self.core_keywords['tier1']):
            score += 0.4

        # Tier 2: 시술/진료 키워드 (0.3)
        if any(term in keyword_lower for term in self.core_keywords['tier2']):
            score += 0.3

        # Tier 3: 지역 키워드 (0.2)
        if any(term in keyword_lower for term in self.core_keywords['tier3']):
            score += 0.2

        # 전환 의도 키워드 보너스 (0.1)
        intent_keywords = ['가격', '비용', '후기', '추천', '예약', '잘하는']
        if any(term in keyword_lower for term in intent_keywords):
            score += 0.1

        return min(score, 1.0)

    def filter_batch(self, keywords: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        배치 필터링

        Returns:
            (통과 목록, 제외 목록 [(키워드, 사유)])
        """
        passed = []
        rejected = []

        for kw in keywords:
            result = self.validate(kw)
            if result.is_valid:
                passed.append(kw)
            else:
                rejected.append((kw, result.reason))

        return passed, rejected

    def filter_with_scores(self, keywords: List[str]) -> List[Tuple[str, float]]:
        """
        점수와 함께 필터링

        Returns:
            [(키워드, 관련성점수)] - 유효한 키워드만
        """
        results = []
        for kw in keywords:
            result = self.validate(kw)
            if result.is_valid:
                results.append((kw, result.relevance_score))

        # 관련성 점수 내림차순 정렬
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_stats(self, passed: List[str], rejected: List[Tuple[str, str]]) -> Dict:
        """필터링 통계"""
        total = len(passed) + len(rejected)
        rejection_reasons = {}
        for _, reason in rejected:
            base_reason = reason.split(':')[0]  # blacklisted:xxx -> blacklisted
            rejection_reasons[base_reason] = rejection_reasons.get(base_reason, 0) + 1

        return {
            'total': total,
            'passed': len(passed),
            'rejected': len(rejected),
            'pass_rate': len(passed) / total * 100 if total > 0 else 0,
            'rejection_reasons': rejection_reasons
        }


class KeywordBlacklist:
    """블랙리스트 관리"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = Path(__file__).parent.parent / 'config' / 'blacklist.json'
        else:
            self.config_path = Path(config_path)

        self.data = self._load()

    def _load(self) -> Dict:
        """블랙리스트 로드"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'keywords': [], 'competitors': [], 'patterns': []}

    def save(self):
        """블랙리스트 저장"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_keyword(self, keyword: str):
        """키워드 추가"""
        if keyword not in self.data['keywords']:
            self.data['keywords'].append(keyword)
            self.save()

    def add_competitor(self, name: str):
        """경쟁사 추가"""
        if name not in self.data['competitors']:
            self.data['competitors'].append(name)
            self.save()

    def remove_keyword(self, keyword: str):
        """키워드 제거"""
        if keyword in self.data['keywords']:
            self.data['keywords'].remove(keyword)
            self.save()

    def get_all(self) -> Set[str]:
        """모든 블랙리스트 항목"""
        return set(self.data['keywords'] + self.data['competitors'])


# 테스트 코드
if __name__ == '__main__':
    filter = KeywordQualityFilter()

    test_keywords = [
        "청주 다이어트 한의원",  # 유효, 높은 관련성
        "청주 한의원 가격",  # 유효, 높은 관련성
        "ㅋㅋㅋㅋ",  # 스팸
        "test!@#",  # 특수문자
        "a",  # 너무 짧음
        "서울 맛집",  # 유효하지만 낮은 관련성
        "청주 허리 통증",  # 유효, 중간 관련성
    ]

    passed, rejected = filter.filter_batch(test_keywords)

    print("=== 필터링 결과 ===")
    print(f"통과: {passed}")
    print(f"제외: {rejected}")

    stats = filter.get_stats(passed, rejected)
    print(f"\n통계: {stats}")
