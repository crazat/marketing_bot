"""
Lead Scoring Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 1.3] 리드 스코어링 시스템
- 소스 신뢰도, 콘텐츠 관련성, 시간 신선도, 참여도를 기반으로 0-100점 산정
- 리드 우선순위화를 통해 전환율 향상

[Phase 4.0] 개선사항
- 외부 설정 파일(scoring_config.json) 지원
- 지역/키워드 설정 분리

[Phase 5.1] 5차원 다차원 스코어링 시스템
- Conversion Probability: 플랫폼 기반 전환 확률 예측
- Urgency Score: 긴급 대응 필요 여부 (시간 민감도)
- Revenue Potential: 예상 수익 잠재력
- Fit Score: 서비스 매칭도
- Trust Score: TrustScorer에서 계산 (기존)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from pathlib import Path
import json
import re
import logging
import os
import hashlib

logger = logging.getLogger(__name__)

# 설정 파일 경로 (프로젝트 루트/config)
CONFIG_PATH = Path(__file__).parent.parent.parent.parent / 'config' / 'scoring_config.json'


def load_scoring_config() -> Dict[str, Any]:
    """외부 설정 파일 로드 (없으면 빈 딕셔너리 반환)"""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"설정 파일 로드 실패: {e}")
    return {}


class LeadScorer:
    """
    리드(잠재고객)에 대한 점수를 계산하는 클래스.
    점수 범위: 0-100
    등급:
        - 🔴 80-100: Hot Lead (즉시 연락)
        - 🟡 60-79: Warm Lead (1일 내 연락)
        - 🟢 40-59: Cool Lead (주간 리뷰)
        - ⚪ 0-39: Cold Lead (자동 보관)

    [P2-2] 외부 설정 파일(scoring_config.json) 지원
    [Phase 5.0] opportunity_bonus 추가 - 기회 점수
    """

    # [Phase 5.0] opportunity_bonus는 기존 breakdown 점수를 재활용
    # (별도 키워드 리스트 제거 - 기존 ENGAGEMENT_KEYWORDS와 중복되므로)

    # 기본값 (설정 파일 없을 때 사용)
    DEFAULT_SOURCE_SCORES = {
        'cafe': 30, 'naver_cafe': 30, 'mom_cafe': 30,
        'youtube': 28, 'youtube_comment': 25,
        'instagram': 22, 'tiktok': 20,
        'blog': 18, 'naver_blog': 18,
        'carrot': 15, 'influencer': 25,
        'kin': 28, 'naver_kin': 28,
    }

    DEFAULT_HIGH_RELEVANCE = [
        '한의원', '한약', '다이어트', '청주', '규림',
        '추천', '후기', '효과', '상담', '진료',
        '체중', '비만', '다이어트한약', '살빼기'
    ]

    DEFAULT_MEDIUM_RELEVANCE = [
        '병원', '의원', '치료', '건강', '약',
        '감량', '식이', '운동', '몸무게'
    ]

    DEFAULT_NEGATIVE = [
        '광고', '협찬', '제공', '원고료', '체험단',
        '서울', '부산', '대구', '인천', '대전'
    ]

    DEFAULT_ENGAGEMENT = [
        '질문', '궁금', '어디', '추천해주세요', '알려주세요',
        '가격', '비용', '얼마', '예약', '연락'
    ]

    # [Phase 5.1] 플랫폼별 전환율 (실제 데이터 기반 추정치)
    PLATFORM_CONVERSION_RATES = {
        'naver_kin': 0.15,      # 지식인: 질문자 = 높은 니즈
        'kin': 0.15,
        'cafe': 0.12,           # 카페: 커뮤니티 신뢰
        'naver_cafe': 0.12,
        'mom_cafe': 0.14,       # 맘카페: 높은 전환율
        'youtube': 0.08,        # 유튜브: 관심은 있으나 행동 전환 낮음
        'youtube_comment': 0.06,
        'instagram': 0.05,      # SNS: 관심 표현이나 전환 낮음
        'tiktok': 0.04,
        'blog': 0.07,           # 블로그: 정보 탐색 단계
        'naver_blog': 0.07,
        'carrot': 0.03,         # 중고거래: 전환 낮음
        'default': 0.05,
    }

    # [Phase 5.1] 긴급도 키워드
    URGENCY_HIGH_KEYWORDS = [
        '급해요', '급합니다', '오늘', '내일', '당장', '바로',
        '지금', '즉시', '빨리', '언제', '시간'
    ]
    URGENCY_MEDIUM_KEYWORDS = [
        '이번주', '이번 주', '다음주', '다음 주', '곧', '조만간'
    ]

    # [Phase 5.1] 수익 잠재력 키워드 (고가 서비스 관련)
    HIGH_REVENUE_KEYWORDS = [
        '프리미엄', '패키지', '장기', '1개월', '2개월', '3개월',
        '한약', '다이어트 한약', '체중감량', '비만', '전신',
        '가족', '부부', '함께'
    ]
    MEDIUM_REVENUE_KEYWORDS = [
        '상담', '진료', '치료', '교정', '관리'
    ]

    # [Phase 5.1] 서비스 매칭 키워드 (업체 특화 서비스)
    PRIMARY_SERVICE_KEYWORDS = [
        '다이어트', '체중', '살', '비만', '한약', '감량',
        '다이어트한약', '체중감량', '살빼기'
    ]
    SECONDARY_SERVICE_KEYWORDS = [
        '한의원', '한방', '침', '뜸', '추나', '교정',
        '통증', '허리', '어깨', '목', '관절'
    ]

    def __init__(self):
        """설정 파일에서 키워드 로드 (없으면 기본값 사용)"""
        config = load_scoring_config()
        lead_config = config.get('lead_scoring', {})

        # 소스 점수
        self.SOURCE_SCORES = config.get('source_scores', self.DEFAULT_SOURCE_SCORES)

        # 고관련성 키워드 (여러 카테고리 병합)
        high_rel = lead_config.get('high_relevance_keywords', {})
        if high_rel:
            self.HIGH_RELEVANCE_KEYWORDS = self._flatten_keywords(high_rel)
        else:
            self.HIGH_RELEVANCE_KEYWORDS = self.DEFAULT_HIGH_RELEVANCE

        # 중관련성 키워드
        med_rel = lead_config.get('medium_relevance_keywords', {})
        if med_rel:
            self.MEDIUM_RELEVANCE_KEYWORDS = self._flatten_keywords(med_rel)
        else:
            self.MEDIUM_RELEVANCE_KEYWORDS = self.DEFAULT_MEDIUM_RELEVANCE

        # 부정 키워드
        neg = lead_config.get('negative_keywords', {})
        if neg:
            self.NEGATIVE_KEYWORDS = self._flatten_keywords(neg)
        else:
            self.NEGATIVE_KEYWORDS = self.DEFAULT_NEGATIVE

        # 참여 키워드
        eng = lead_config.get('engagement_keywords', {})
        if eng:
            self.ENGAGEMENT_KEYWORDS = self._flatten_keywords(eng)
        else:
            self.ENGAGEMENT_KEYWORDS = self.DEFAULT_ENGAGEMENT

        logger.debug(f"LeadScorer 초기화: 고관련성 {len(self.HIGH_RELEVANCE_KEYWORDS)}개, "
                    f"중관련성 {len(self.MEDIUM_RELEVANCE_KEYWORDS)}개, "
                    f"부정 {len(self.NEGATIVE_KEYWORDS)}개")

    def _flatten_keywords(self, keyword_dict: Dict[str, Any]) -> List[str]:
        """중첩된 키워드 딕셔너리를 평탄화"""
        keywords = []
        for key, value in keyword_dict.items():
            if key == 'description':
                continue
            if isinstance(value, list):
                keywords.extend(value)
            elif isinstance(value, str):
                keywords.append(value)
        return keywords

    def calculate_score(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        리드에 대한 종합 점수 계산

        Args:
            lead: 리드 데이터 딕셔너리
                - source/platform: 출처
                - title: 제목
                - content: 내용
                - created_at/scraped_at: 생성일
                - url: URL

        Returns:
            {
                'score': 총점 (0-100),
                'grade': 등급 (hot/warm/cool/cold),
                'breakdown': {
                    'source': 소스 점수,
                    'relevance': 관련성 점수,
                    'freshness': 신선도 점수,
                    'engagement': 참여도 점수
                }
            }
        """
        breakdown = {
            'source': 0,
            'relevance': 0,
            'freshness': 0,
            'engagement': 0
        }

        # 1. 소스 신뢰도 점수 (30점 만점)
        source = (lead.get('platform') or lead.get('source') or '').lower()
        for key, score in self.SOURCE_SCORES.items():
            if key in source:
                breakdown['source'] = score
                break
        if breakdown['source'] == 0:
            breakdown['source'] = 10  # 기본 점수

        # 2. 콘텐츠 관련성 점수 (30점 만점)
        title = (lead.get('title') or '').lower()
        content = (lead.get('content') or lead.get('summary') or '').lower()
        full_text = f"{title} {content}"

        relevance_score = 0

        # 고관련성 키워드
        high_matches = sum(1 for kw in self.HIGH_RELEVANCE_KEYWORDS if kw in full_text)
        relevance_score += min(high_matches * 6, 18)  # 최대 18점

        # 중관련성 키워드
        medium_matches = sum(1 for kw in self.MEDIUM_RELEVANCE_KEYWORDS if kw in full_text)
        relevance_score += min(medium_matches * 3, 9)  # 최대 9점

        # 부정 키워드 감점
        negative_matches = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in full_text)
        relevance_score -= negative_matches * 5

        breakdown['relevance'] = max(0, min(30, relevance_score))

        # 3. 시간 신선도 점수 (20점 만점)
        created_at = lead.get('created_at') or lead.get('scraped_at') or lead.get('date_posted')
        freshness_score = self._calculate_freshness(created_at)
        breakdown['freshness'] = freshness_score

        # 4. 참여도 점수 (20점 만점)
        engagement_score = 0

        # 참여 키워드 확인
        engagement_matches = sum(1 for kw in self.ENGAGEMENT_KEYWORDS if kw in full_text)
        engagement_score += min(engagement_matches * 4, 12)

        # 제목에 질문 형태가 있는지
        if any(q in title for q in ['?', '어디', '추천', '질문', '궁금']):
            engagement_score += 5

        # URL이 있으면 접근 가능
        if lead.get('url'):
            engagement_score += 3

        breakdown['engagement'] = min(20, engagement_score)

        # 총점 계산
        total_score = sum(breakdown.values())
        total_score = max(0, min(100, total_score))

        # 등급 결정
        grade = self._determine_grade(total_score)

        # [Phase 5.0] opportunity_bonus 계산 (별도 보너스, 총점에는 미포함)
        opportunity_bonus = self._calculate_opportunity_bonus(lead, breakdown)

        # [Phase 5.1] 5차원 다차원 스코어링
        multi_dimensional = self._calculate_multi_dimensional_score(lead, full_text, breakdown)

        return {
            'score': total_score,
            'grade': grade,
            'breakdown': breakdown,
            'opportunity_bonus': opportunity_bonus,  # [Phase 5.0]
            'multi_dimensional': multi_dimensional,  # [Phase 5.1] 5차원 스코어링
        }

    def _calculate_freshness(self, date_str: Optional[str]) -> int:
        """
        날짜 문자열에서 신선도 점수 계산 (20점 만점)
        - 오늘: 20점
        - 1일: 18점
        - 2일: 16점
        - 3일: 14점
        - 4-7일: 10점
        - 8-14일: 6점
        - 15-30일: 3점
        - 30일+: 0점
        """
        if not date_str:
            return 5  # 날짜 정보 없으면 기본값

        try:
            # 다양한 날짜 형식 파싱 시도
            now = datetime.now()

            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y.%m.%d']:
                try:
                    dt = datetime.strptime(str(date_str)[:19], fmt)
                    break
                except ValueError:
                    continue
            else:
                return 5  # 파싱 실패시 기본값

            days_old = (now - dt).days

            if days_old <= 0:
                return 20
            elif days_old == 1:
                return 18
            elif days_old == 2:
                return 16
            elif days_old == 3:
                return 14
            elif days_old <= 7:
                return 10
            elif days_old <= 14:
                return 6
            elif days_old <= 30:
                return 3
            else:
                return 0

        except Exception as e:
            logger.debug(f"Date parsing error: {e}")
            return 5

    def _determine_grade(self, score: int) -> str:
        """점수에 따른 등급 결정"""
        if score >= 80:
            return 'hot'
        elif score >= 60:
            return 'warm'
        elif score >= 40:
            return 'cool'
        else:
            return 'cold'

    def _calculate_opportunity_bonus(self, lead: Dict[str, Any], breakdown: Dict[str, int]) -> int:
        """
        [Phase 5.0] 기회 보너스 점수 계산 (최대 15점)

        기존 breakdown 점수를 재활용하여 중복 키워드 검사 제거:
        - 높은 engagement 점수 (+5점): engagement >= 12 (이미 질문/참여 키워드 반영됨)
        - 최근 48시간 이내 (+5점): freshness >= 18
        - 댓글 0~2개 게시물 (+5점): 개입 용이성

        Args:
            lead: 리드 데이터
            breakdown: 기존 스코어 breakdown

        Returns:
            opportunity_bonus: 0-15점
        """
        bonus = 0

        # 1. 높은 engagement 점수 (+5점) - 이미 질문/참여 키워드 검사 완료됨
        if breakdown.get('engagement', 0) >= 12:
            bonus += 5

        # 2. 최근 48시간 이내 (+5점) - freshness 18점 이상
        if breakdown.get('freshness', 0) >= 18:
            bonus += 5

        # 3. 댓글 0~2개 게시물 (+5점) - 개입 용이성
        comment_count = lead.get('comment_count', lead.get('comments', 0))
        if isinstance(comment_count, int) and comment_count <= 2:
            bonus += 5

        return min(15, bonus)  # 최대 15점

    def _calculate_multi_dimensional_score(
        self,
        lead: Dict[str, Any],
        full_text: str,
        breakdown: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        [Phase 5.1] 5차원 다차원 스코어링 계산

        차원:
        1. conversion_probability: 전환 확률 (0.0-1.0)
        2. urgency_score: 긴급도 점수 (0-100)
        3. revenue_potential: 수익 잠재력 (low/medium/high/premium)
        4. fit_score: 서비스 매칭도 (0-100)
        5. priority_rank: 종합 우선순위 (1=최우선, 5=보류)

        Args:
            lead: 리드 데이터
            full_text: 제목+내용 결합 텍스트
            breakdown: 기존 스코어 breakdown

        Returns:
            multi_dimensional: 5차원 점수 딕셔너리
        """
        # 1. 전환 확률 계산
        conversion_probability = self._calculate_conversion_probability(lead, breakdown)

        # 2. 긴급도 점수 계산
        urgency_score = self._calculate_urgency_score(full_text, breakdown)

        # 3. 수익 잠재력 계산
        revenue_potential = self._calculate_revenue_potential(full_text)

        # 4. 서비스 매칭도 계산
        fit_score = self._calculate_fit_score(full_text)

        # 5. 종합 우선순위 계산 (1-5등급)
        priority_rank = self._calculate_priority_rank(
            conversion_probability, urgency_score, revenue_potential, fit_score
        )

        return {
            'conversion_probability': round(conversion_probability, 3),
            'urgency_score': urgency_score,
            'revenue_potential': revenue_potential,
            'fit_score': fit_score,
            'priority_rank': priority_rank,
        }

    def _calculate_conversion_probability(
        self,
        lead: Dict[str, Any],
        breakdown: Dict[str, int]
    ) -> float:
        """
        [Phase 5.1] 전환 확률 계산

        플랫폼 기본 전환율 + 콘텐츠 품질 보정

        Returns:
            0.0 ~ 1.0 사이의 전환 확률
        """
        # 플랫폼 기본 전환율
        platform = (lead.get('platform') or lead.get('source') or '').lower()
        base_rate = self.PLATFORM_CONVERSION_RATES.get('default')

        for key, rate in self.PLATFORM_CONVERSION_RATES.items():
            if key in platform:
                base_rate = rate
                break

        # 콘텐츠 품질 보정
        # engagement 점수가 높으면 전환율 상승
        engagement_multiplier = 1.0 + (breakdown.get('engagement', 0) / 100)

        # freshness 점수가 높으면 전환율 상승 (최근 콘텐츠 = 활발한 관심)
        freshness_multiplier = 1.0 + (breakdown.get('freshness', 0) / 200)

        # relevance 점수가 높으면 전환율 상승
        relevance_multiplier = 1.0 + (breakdown.get('relevance', 0) / 150)

        # 최종 전환율 계산 (최대 0.5 = 50%)
        probability = base_rate * engagement_multiplier * freshness_multiplier * relevance_multiplier
        return min(0.5, probability)

    def _calculate_urgency_score(self, full_text: str, breakdown: Dict[str, int]) -> int:
        """
        [Phase 5.1] 긴급도 점수 계산 (0-100)

        - 긴급 키워드 포함 여부
        - 콘텐츠 신선도
        - 질문/요청 형태

        Returns:
            0-100 사이의 긴급도 점수
        """
        score = 0

        # 1. 긴급 키워드 확인 (최대 40점)
        high_urgency_count = sum(1 for kw in self.URGENCY_HIGH_KEYWORDS if kw in full_text)
        medium_urgency_count = sum(1 for kw in self.URGENCY_MEDIUM_KEYWORDS if kw in full_text)

        score += min(high_urgency_count * 15, 30)  # 고긴급 키워드
        score += min(medium_urgency_count * 5, 10)  # 중긴급 키워드

        # 2. 신선도 기반 긴급도 (최대 30점)
        freshness = breakdown.get('freshness', 0)
        if freshness >= 18:  # 48시간 이내
            score += 30
        elif freshness >= 14:  # 3일 이내
            score += 20
        elif freshness >= 10:  # 1주일 이내
            score += 10

        # 3. 질문/요청 형태 (최대 20점)
        if '?' in full_text:
            score += 10
        if any(kw in full_text for kw in ['추천해주세요', '알려주세요', '도와주세요']):
            score += 10

        # 4. engagement 점수 반영 (최대 10점)
        engagement = breakdown.get('engagement', 0)
        score += min(engagement // 2, 10)

        return min(100, score)

    def _calculate_revenue_potential(self, full_text: str) -> str:
        """
        [Phase 5.1] 수익 잠재력 계산

        Returns:
            'premium' | 'high' | 'medium' | 'low'
        """
        high_count = sum(1 for kw in self.HIGH_REVENUE_KEYWORDS if kw in full_text)
        medium_count = sum(1 for kw in self.MEDIUM_REVENUE_KEYWORDS if kw in full_text)

        # 복수 언급 (가족, 장기 등) → premium
        if high_count >= 3:
            return 'premium'
        elif high_count >= 2:
            return 'high'
        elif high_count >= 1 or medium_count >= 2:
            return 'medium'
        else:
            return 'low'

    def _calculate_fit_score(self, full_text: str) -> int:
        """
        [Phase 5.1] 서비스 매칭도 계산 (0-100)

        업체 특화 서비스와의 매칭도

        Returns:
            0-100 사이의 매칭도 점수
        """
        score = 0

        # 1. 주요 서비스 키워드 (최대 60점)
        primary_count = sum(1 for kw in self.PRIMARY_SERVICE_KEYWORDS if kw in full_text)
        score += min(primary_count * 15, 60)

        # 2. 보조 서비스 키워드 (최대 30점)
        secondary_count = sum(1 for kw in self.SECONDARY_SERVICE_KEYWORDS if kw in full_text)
        score += min(secondary_count * 10, 30)

        # 3. 지역 매칭 보너스 (최대 10점)
        if '청주' in full_text:
            score += 10

        return min(100, score)

    def _calculate_priority_rank(
        self,
        conversion_probability: float,
        urgency_score: int,
        revenue_potential: str,
        fit_score: int
    ) -> int:
        """
        [Phase 5.1] 종합 우선순위 계산

        Returns:
            1: 최우선 (즉시 대응)
            2: 높음 (당일 대응)
            3: 중간 (2-3일 내 대응)
            4: 낮음 (주간 리뷰)
            5: 보류 (자동 보관)
        """
        # 점수 합산 (가중치 적용)
        revenue_scores = {'premium': 30, 'high': 20, 'medium': 10, 'low': 0}

        total_score = (
            conversion_probability * 100 * 0.25 +  # 전환 확률 25%
            urgency_score * 0.30 +                  # 긴급도 30%
            revenue_scores.get(revenue_potential, 0) +  # 수익 잠재력
            fit_score * 0.25                         # 서비스 매칭 25%
        )

        # 등급 결정
        if total_score >= 70:
            return 1  # 최우선
        elif total_score >= 55:
            return 2  # 높음
        elif total_score >= 40:
            return 3  # 중간
        elif total_score >= 25:
            return 4  # 낮음
        else:
            return 5  # 보류

    def get_grade_emoji(self, grade: str) -> str:
        """등급에 해당하는 이모지 반환"""
        return {
            'hot': '🔴',
            'warm': '🟡',
            'cool': '🟢',
            'cold': '⚪'
        }.get(grade, '⚪')

    def get_grade_label(self, grade: str) -> str:
        """등급에 해당하는 한글 라벨 반환"""
        return {
            'hot': 'Hot Lead',
            'warm': 'Warm Lead',
            'cool': 'Cool Lead',
            'cold': 'Cold Lead'
        }.get(grade, 'Cold Lead')

    def batch_score(self, leads: list) -> list:
        """
        여러 리드를 한 번에 스코어링

        Args:
            leads: 리드 딕셔너리 리스트

        Returns:
            점수 정보가 추가된 리드 리스트
        """
        scored_leads = []

        for lead in leads:
            try:
                score_result = self.calculate_score(lead)
                lead['score'] = score_result['score']
                lead['grade'] = score_result['grade']
                lead['score_breakdown'] = score_result['breakdown']
                lead['opportunity_bonus'] = score_result.get('opportunity_bonus', 0)  # [Phase 5.0]
                lead['multi_dimensional'] = score_result.get('multi_dimensional', {})  # [Phase 5.1]
                lead['priority_rank'] = score_result.get('multi_dimensional', {}).get('priority_rank', 5)
                scored_leads.append(lead)
            except Exception as e:
                logger.error(f"Lead scoring error: {e}")
                lead['score'] = 0
                lead['grade'] = 'cold'
                lead['score_breakdown'] = {}
                lead['opportunity_bonus'] = 0
                lead['multi_dimensional'] = {}
                lead['priority_rank'] = 5
                scored_leads.append(lead)

        return scored_leads


class TrustScorer:
    """
    [Phase 4.0] 리드 신뢰도 점수 계산
    [Phase 5.0] engagement_signal 분류 추가

    주요 탐지 대상:
    1. 바이럴 마케팅 (광고인 듯 아닌 듯한 콘텐츠)
    2. 명백한 스팸/광고성 콘텐츠
    3. 중복 콘텐츠

    점수 범위: 0-100
    등급:
        - 🟢 70-100: 신뢰 (실제 문의/후기로 추정)
        - 🟡 40-69: 확인 필요 (바이럴 마케팅 가능성)
        - 🔴 0-39: 의심 (광고/스팸 가능성 높음)

    engagement_signal (Phase 5.0):
        - seeking_info: 정보 탐색 중 (질문형)
        - ready_to_act: 행동 준비됨 (예약, 비교 언급)
        - passive: 일반 언급
    """

    # [P3-1] 중복 콘텐츠 탐지용 해시 저장소 (싱글톤 공유)
    _content_hashes: Dict[str, List[str]] = {}  # {hash: [lead_ids]}
    _content_cache_size = 10000  # 최대 캐시 크기

    # [Phase 5.0] engagement_signal 분류
    # - seeking_info: GENUINE_INQUIRY_PATTERNS 재활용 (중복 제거)
    # - ready_to_act: 구체적인 행동 의도 패턴만 유지
    READY_TO_ACT_PATTERNS = [
        r'예약.*하려',
        r'예약.*할',
        r'방문.*하려',
        r'가보려',
        r'결정.*했',
        r'다음\s*주.*가',
        r'이번\s*주.*가',
        r'내일.*가',
        r'오늘.*가',
    ]

    # ========================================
    # 바이럴 마케팅 탐지 패턴 (광고인 듯 아닌 듯)
    # ========================================

    # 체험단/협찬 의심 키워드
    SPONSORED_KEYWORDS = [
        '제공받', '협찬', '체험단', '원고료', '광고',
        '소정의', '지원받', '서비스 제공', '무상으로',
    ]

    # 바이럴 마케팅 특유의 과장 표현
    # [Phase 4.0] 완화됨 - 일반 고객도 사용하는 표현 제외
    # "진짜 좋아요", "강력 추천" 등은 만족한 고객도 자연스럽게 사용
    EXAGGERATED_EXPRESSIONS = [
        r'인생.*(맛집|병원|한의원)',            # "인생 한의원" - 마케팅 특유 표현
        r'무조건.*(추천|가세요|가보세요)',      # "무조건 추천" - 광고성 강함
        r'(안 ?가면|안 ?하면).*(후회|손해)',    # "안 가면 후회" - 압박성 표현
        # 제거됨: "진짜 좋아요", "강력 추천", "정말 만족" 등은 일반 표현
    ]

    # 바이럴 마케팅 문체 패턴
    # [Phase 4.0] 대폭 축소됨 - 일반적인 표현 제외
    # "친구 추천 받아서", "검색하다 발견" 등은 자연스러운 표현
    VIRAL_WRITING_PATTERNS = [
        r'내돈내산',                            # 광고 의심 방어용 표현
        # 제거됨: "저도 ~했는데", "여기서 ~받았는데" 등 일반 표현
        # 제거됨: "솔직 후기" - Task #97에서 제거 결정
    ]

    # 업체 홍보 의심 상세 정보 나열
    # [Phase 4.0] 대폭 완화됨 - 상세 정보 나열은 정보 공유 목적일 수 있음
    # 실제 방문 후기에서도 주소, 영업시간, 가격 등을 언급하는 것은 자연스러움
    PROMOTIONAL_DETAILS = [
        # 제거됨: 주소, 전화, 영업시간, 가격, 주차, 예약 등
        # 이런 정보 나열만으로 홍보라고 판단하는 것은 과도함
    ]

    # ========================================
    # 명백한 스팸/광고 패턴
    # ========================================

    # 스팸 URL 패턴
    SPAM_URL_PATTERNS = [
        r'bit\.ly|goo\.gl|tinyurl|t\.co',  # 단축 URL
        r'click|redirect|track',            # 추적 링크
    ]

    # 직접적인 광고/CTA 패턴
    SPAM_CONTENT_PATTERNS = [
        r'클릭.*하세요|지금.*신청',            # CTA
        r'선착순|한정.*수량|마감.*임박',       # 긴급성 유도
        r'↓↓|→→|☞|☎|📞',                     # 과도한 기호
        r'010-?\d{4}-?\d{4}',                  # 전화번호 직접 노출
        r'카톡\s*[:：]?\s*[a-zA-Z0-9_]+',     # 카톡 ID 홍보
    ]

    # ========================================
    # 진짜 문의/고민 판별 지표
    # ========================================

    # 실제 문의/고민 표현
    GENUINE_INQUIRY_PATTERNS = [
        r'(어디|어떤|뭐가|뭘).*(좋을까|괜찮을까|나을까)',  # 질문형
        r'추천.*해\s*주세요|알려\s*주세요',                 # 도움 요청
        r'고민.*(중|이에요|입니다)',                        # 고민 표현
        r'처음.*인데|초보.*인데',                           # 초심자 표현
        r'\?$',                                              # 질문으로 끝남
    ]

    # 부정적 경험 언급 (진짜 후기 가능성)
    NEGATIVE_MENTIONS = [
        '별로', '아쉬', '단점', '불편', '비싸', '실망',
        '그냥', '보통', '애매', '글쎄',
    ]

    # 신뢰 지표 (기존 유지하되 의미 재해석)
    TRUST_INDICATORS = [
        '후기', '경험', '직접', '방문', '진료',
        '추천', '감사', '선생님', '원장님',
    ]

    def calculate_trust_score(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        리드 신뢰도 점수 계산

        주요 분석:
        1. 바이럴 마케팅 탐지 (가장 중요)
        2. 명백한 스팸/광고 탐지
        3. 진짜 문의/고민 판별
        4. 중복 콘텐츠 탐지

        Returns:
            {
                'trust_score': 0-100,
                'trust_level': 'trusted' | 'review' | 'suspicious',
                'trust_reasons': ['reason1', 'reason2', ...]
            }
        """
        score = 60  # 기본 점수 (중립에서 시작)
        reasons = []

        author = (lead.get('author') or lead.get('target_name') or '').strip()
        title = (lead.get('title') or '').strip()
        content = (lead.get('content') or lead.get('summary') or '').strip()
        url = (lead.get('url') or '').strip()
        full_text = f"{title} {content}"

        # 1. [핵심] 바이럴 마케팅 탐지 (최대 -40점)
        viral_score = self._analyze_viral_marketing(full_text)
        score += viral_score['delta']
        reasons.extend(viral_score['reasons'])

        # 2. 명백한 스팸/광고 탐지 (최대 -30점)
        spam_score = self._analyze_spam_content(full_text)
        score += spam_score['delta']
        reasons.extend(spam_score['reasons'])

        # 3. 진짜 문의/고민 판별 (최대 +25점)
        genuine_score = self._analyze_genuine_inquiry(full_text)
        score += genuine_score['delta']
        reasons.extend(genuine_score['reasons'])

        # 4. URL 분석 (최대 -15점)
        url_score = self._analyze_url(url)
        score += url_score['delta']
        reasons.extend(url_score['reasons'])

        # 5. 플랫폼 신뢰도 (최대 +15점)
        platform = (lead.get('platform') or lead.get('source') or '').lower()
        platform_score = self._analyze_platform(platform)
        score += platform_score['delta']
        reasons.extend(platform_score['reasons'])

        # 6. 중복 콘텐츠 분석 (최대 -20점)
        lead_id = str(lead.get('id') or lead.get('url') or '')
        dup_score = self._analyze_duplicate(full_text, lead_id)
        score += dup_score['delta']
        reasons.extend(dup_score['reasons'])

        # 7. 작성자 분석 (간소화됨, 최대 -15점)
        author_score = self._analyze_author(author)
        score += author_score['delta']
        reasons.extend(author_score['reasons'])

        # 점수 범위 제한
        score = max(0, min(100, score))

        # 신뢰 등급 결정
        if score >= 70:
            trust_level = 'trusted'
        elif score >= 40:
            trust_level = 'review'
        else:
            trust_level = 'suspicious'

        # [Phase 5.0] engagement_signal 분류
        engagement_signal = self._classify_engagement_signal(full_text)

        return {
            'trust_score': score,
            'trust_level': trust_level,
            'trust_reasons': reasons[:5],  # 상위 5개 이유만
            'engagement_signal': engagement_signal  # [Phase 5.0] 신규 필드
        }

    def _analyze_author(self, author: str) -> Dict[str, Any]:
        """
        작성자 분석 [대폭 간소화]

        대부분의 사용자가 닉네임을 사용하므로,
        닉네임 형태로 봇/스팸 여부를 판단하지 않음.
        오직 명백한 시스템 계정명만 감점.
        """
        delta = 0
        reasons = []

        if not author:
            # 작성자 정보 없음은 약간의 감점만
            return {'delta': -5, 'reasons': ['작성자 정보 없음']}

        author_lower = author.lower().strip()

        # 명백한 시스템/테스트 계정만 감점
        system_patterns = [
            r'^(admin|root|guest|test|system|bot)$',  # 정확히 일치
            r'^(운영자|관리자|시스템|테스트)$',
        ]

        for pattern in system_patterns:
            if re.search(pattern, author_lower):
                delta -= 15
                reasons.append('시스템/테스트 계정명')
                break

        # 닉네임 형태로는 판단하지 않음
        # (대부분의 정상 사용자도 닉네임 사용)

        return {'delta': delta, 'reasons': reasons}

    def _analyze_viral_marketing(self, content: str) -> Dict[str, Any]:
        """
        [핵심] 바이럴 마케팅 탐지

        광고인 듯 아닌 듯한 콘텐츠를 감지합니다.
        - 체험단/협찬 의심
        - 과장된 표현
        - 바이럴 마케팅 특유의 문체
        - 업체 홍보용 상세 정보 나열

        Returns:
            {'delta': -40 ~ 0, 'reasons': [...]}
        """
        delta = 0
        reasons = []

        if not content:
            return {'delta': 0, 'reasons': []}

        content_lower = content.lower()

        # 1. 체험단/협찬 키워드 (가장 명확한 지표)
        sponsored_count = sum(1 for kw in self.SPONSORED_KEYWORDS if kw in content)
        if sponsored_count >= 2:
            delta -= 25
            reasons.append('체험단/협찬 의심 (다수 키워드)')
        elif sponsored_count == 1:
            delta -= 15
            reasons.append('협찬 관련 키워드 포함')

        # 2. 과장된 표현 패턴 (완화됨 - 명백한 마케팅 표현만 감점)
        exaggerated_count = 0
        for pattern in self.EXAGGERATED_EXPRESSIONS:
            if re.search(pattern, content):
                exaggerated_count += 1

        if exaggerated_count >= 2:
            delta -= 10
            reasons.append('마케팅 특유 과장 표현')
        elif exaggerated_count >= 1:
            delta -= 5
            reasons.append('과장된 표현 포함')

        # 3. 바이럴 마케팅 문체
        viral_style_count = 0
        for pattern in self.VIRAL_WRITING_PATTERNS:
            if re.search(pattern, content):
                viral_style_count += 1

        if viral_style_count >= 2:
            delta -= 15
            reasons.append('바이럴 마케팅 문체')

        # [Phase 4.0] 제거됨: 업체 정보 나열 감점 로직
        # 이유: 주소, 가격, 영업시간 등 상세 정보는 정보 공유 목적일 수 있음
        # 실제 방문 후기에서도 이런 정보를 공유하는 것은 자연스러움

        # [Phase 4.0] 제거됨: "솔직 후기 + 부정 없음 = 의심" 로직
        # 이유: 정말 만족한 고객도 "솔직히 다 좋았어요"라고 쓸 수 있음
        # 부정적 언급 유무로 진정성을 판단하는 것은 과도함

        return {'delta': max(-40, delta), 'reasons': reasons}

    def _analyze_spam_content(self, content: str) -> Dict[str, Any]:
        """
        명백한 스팸/광고 콘텐츠 탐지

        Returns:
            {'delta': -30 ~ 0, 'reasons': [...]}
        """
        delta = 0
        reasons = []

        if not content:
            return {'delta': -10, 'reasons': ['콘텐츠 없음']}

        # 너무 짧은 콘텐츠
        if len(content) < 20:
            delta -= 10
            reasons.append('너무 짧은 콘텐츠')

        # 직접적인 광고/CTA 패턴
        for pattern in self.SPAM_CONTENT_PATTERNS:
            if re.search(pattern, content):
                delta -= 15
                reasons.append('직접적 광고 패턴')
                break

        # 특수문자/이모지 과다 (스팸 특징)
        special_ratio = len(re.findall(r'[^\w\s가-힣]', content)) / max(len(content), 1)
        if special_ratio > 0.15:
            delta -= 10
            reasons.append('특수문자/이모지 과다')

        return {'delta': max(-30, delta), 'reasons': reasons}

    def _analyze_genuine_inquiry(self, content: str) -> Dict[str, Any]:
        """
        진짜 문의/고민 판별

        실제 정보를 찾는 사람의 게시물 특성을 감지합니다.
        - 질문형 문장
        - 도움 요청 표현
        - 고민/불확실성 표현
        - 부정적 경험 언급 (진짜 후기 가능성)

        Returns:
            {'delta': 0 ~ +25, 'reasons': [...]}
        """
        delta = 0
        reasons = []

        if not content:
            return {'delta': 0, 'reasons': []}

        # 1. 질문형/도움 요청 패턴
        genuine_count = 0
        for pattern in self.GENUINE_INQUIRY_PATTERNS:
            if re.search(pattern, content):
                genuine_count += 1

        if genuine_count >= 2:
            delta += 20
            reasons.append('실제 문의/질문으로 추정')
        elif genuine_count >= 1:
            delta += 10
            reasons.append('질문형 표현 포함')

        # 2. 부정적 경험 언급 (진짜 후기 가능성)
        negative_count = sum(1 for neg in self.NEGATIVE_MENTIONS if neg in content)
        if negative_count >= 2:
            delta += 15
            reasons.append('균형 잡힌 의견 (부정적 언급 포함)')
        elif negative_count >= 1:
            delta += 5

        # 3. 물음표로 끝나는 문장 (실제 질문)
        question_sentences = len(re.findall(r'[가-힣a-zA-Z]+\?', content))
        if question_sentences >= 2:
            delta += 10
            reasons.append('다수의 질문 포함')

        return {'delta': min(25, delta), 'reasons': reasons}

    def _analyze_url(self, url: str) -> Dict[str, Any]:
        """URL 분석"""
        delta = 0
        reasons = []

        if not url:
            return {'delta': -5, 'reasons': ['URL 없음']}

        # 스팸 URL 패턴
        for pattern in self.SPAM_URL_PATTERNS:
            if re.search(pattern, url.lower()):
                delta -= 15
                reasons.append('의심스러운 URL')
                break

        # 신뢰할 수 있는 도메인
        trusted_domains = ['naver.com', 'youtube.com', 'instagram.com', 'tiktok.com', 'daum.net']
        if any(domain in url.lower() for domain in trusted_domains):
            delta += 10
            reasons.append('신뢰 가능한 플랫폼')

        return {'delta': delta, 'reasons': reasons}

    def _analyze_platform(self, platform: str) -> Dict[str, Any]:
        """
        플랫폼 신뢰도 분석

        [Phase 4.0] 평준화됨 - 플랫폼보다 콘텐츠 분석에 더 의존
        - 기존: 2-15점 범위 (7.5배 차이)
        - 개선: 5-10점 범위 (2배 차이)
        - 플랫폼은 참고용이며, 실제 신뢰도는 콘텐츠로 판단
        """
        delta = 0
        reasons = []

        # 플랫폼별 기본 신뢰도 (평준화됨)
        platform_trust = {
            'cafe': 10,        # 커뮤니티 (맘카페 등)
            'naver_cafe': 10,
            'kin': 10,         # 지식인 질문 (실제 문의 가능성)
            'naver_kin': 10,
            'youtube': 8,      # 유튜브 댓글
            'blog': 7,         # 블로그 (광고 가능하나 상세 정보)
            'naver_blog': 7,
            'instagram': 6,    # SNS
            'tiktok': 6,
            'carrot': 5,       # 중고거래 플랫폼
        }

        for key, trust in platform_trust.items():
            if key in platform:
                delta += trust
                break

        # 플랫폼 정보가 없으면 기본 점수
        if delta == 0:
            delta = 6

        return {'delta': delta, 'reasons': reasons}

    # 제거된 메서드:
    # - _analyze_title: _analyze_genuine_inquiry와 _analyze_viral_marketing으로 대체
    # - _analyze_posting_time: 게시 시간으로 봇 판단은 부정확 (야간 근무자, 해외 거주자 등)
    # - _is_likely_real_name: 대부분 닉네임 사용하므로 실명 검증 무의미

    def _analyze_duplicate(self, content: str, lead_id: str) -> Dict[str, Any]:
        """
        [P3-1] 중복 콘텐츠 분석
        - 콘텐츠 해시 기반 중복 감지
        - 동일/유사 콘텐츠 반복 게시 감점

        Args:
            content: 분석할 콘텐츠 (제목 + 내용)
            lead_id: 현재 리드 ID (중복 체크에서 자신 제외용)

        Returns:
            {'delta': 점수 변화, 'reasons': 사유 목록}
        """
        delta = 0
        reasons = []

        if not content or len(content) < 20:
            return {'delta': 0, 'reasons': []}

        # 콘텐츠 정규화 (공백, 특수문자 제거)
        normalized = re.sub(r'\s+', '', content.lower())
        normalized = re.sub(r'[^\w가-힣]', '', normalized)

        # 너무 짧으면 해시 의미 없음
        if len(normalized) < 10:
            return {'delta': 0, 'reasons': []}

        # MD5 해시 생성 (빠른 비교용)
        content_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()

        # 중복 체크
        if content_hash in self._content_hashes:
            existing_ids = self._content_hashes[content_hash]
            # 자기 자신 제외
            other_ids = [id for id in existing_ids if id != lead_id]
            if other_ids:
                duplicate_count = len(other_ids)
                delta -= min(20, 5 * duplicate_count)  # 중복 1개당 -5점, 최대 -20점
                reasons.append(f'동일 콘텐츠 {duplicate_count}회 중복')

                # 현재 ID도 추가 (이미 없으면)
                if lead_id and lead_id not in existing_ids:
                    existing_ids.append(lead_id)
            else:
                # 리스트에 자신만 있으면 신규 추가
                if lead_id and lead_id not in existing_ids:
                    existing_ids.append(lead_id)
        else:
            # 새로운 해시 등록
            if lead_id:
                self._content_hashes[content_hash] = [lead_id]

        # 캐시 크기 제한 (오래된 것 제거)
        if len(self._content_hashes) > self._content_cache_size:
            # 가장 오래된 10% 제거
            to_remove = list(self._content_hashes.keys())[:int(self._content_cache_size * 0.1)]
            for key in to_remove:
                del self._content_hashes[key]

        return {'delta': delta, 'reasons': reasons}

    def _compute_content_similarity(self, content1: str, content2: str) -> float:
        """
        [P3-1] 콘텐츠 유사도 계산 (선택적)
        간단한 Jaccard 유사도 사용

        Returns:
            0.0 ~ 1.0 (1.0이 완전 동일)
        """
        if not content1 or not content2:
            return 0.0

        # 단어 집합 생성
        words1 = set(re.findall(r'[가-힣]+|\w+', content1.lower()))
        words2 = set(re.findall(r'[가-힣]+|\w+', content2.lower()))

        if not words1 or not words2:
            return 0.0

        # Jaccard 유사도
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _classify_engagement_signal(self, content: str) -> str:
        """
        [Phase 5.0] 참여 신호 분류

        분류:
        - seeking_info: 정보를 탐색하는 중 (질문, 추천 요청)
        - ready_to_act: 행동할 준비가 됨 (예약, 방문 계획)
        - passive: 일반적인 언급

        기존 GENUINE_INQUIRY_PATTERNS를 재활용하여 중복 제거

        Args:
            content: 분석할 콘텐츠 (제목 + 내용)

        Returns:
            'seeking_info' | 'ready_to_act' | 'passive'
        """
        if not content:
            return 'passive'

        content_lower = content.lower()

        # 1. ready_to_act 패턴 확인 (우선순위 높음 - 구체적 행동 의도)
        for pattern in self.READY_TO_ACT_PATTERNS:
            if re.search(pattern, content_lower):
                return 'ready_to_act'

        # 2. seeking_info 패턴 확인 (기존 GENUINE_INQUIRY_PATTERNS 재활용)
        for pattern in self.GENUINE_INQUIRY_PATTERNS:
            if re.search(pattern, content_lower):
                return 'seeking_info'

        # 3. 기본값
        return 'passive'

    def batch_calculate(self, leads: list) -> list:
        """여러 리드의 신뢰도 일괄 계산"""
        for lead in leads:
            try:
                trust_result = self.calculate_trust_score(lead)
                lead['trust_score'] = trust_result['trust_score']
                lead['trust_level'] = trust_result['trust_level']
                lead['trust_reasons'] = trust_result['trust_reasons']
                lead['engagement_signal'] = trust_result.get('engagement_signal', 'passive')  # [Phase 5.0]
            except Exception as e:
                logger.error(f"Trust scoring error: {e}")
                lead['trust_score'] = 50
                lead['trust_level'] = 'review'
                lead['trust_reasons'] = []
                lead['engagement_signal'] = 'passive'
        return leads


# 싱글톤 인스턴스
_scorer_instance = None
_trust_scorer_instance = None


def get_lead_scorer() -> LeadScorer:
    """LeadScorer 싱글톤 인스턴스 반환"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = LeadScorer()
    return _scorer_instance


def get_trust_scorer() -> TrustScorer:
    """TrustScorer 싱글톤 인스턴스 반환"""
    global _trust_scorer_instance
    if _trust_scorer_instance is None:
        _trust_scorer_instance = TrustScorer()
    return _trust_scorer_instance
