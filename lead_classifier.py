"""
Lead Classifier Module for Marketing Bot.

YouTube/커뮤니티 댓글에서 진짜 잠재 고객을 찾아냅니다.
- 명확한 구매/예약 의도가 있는 댓글만 High
- 노이즈(홍보, 감상, 짧은 댓글) 적극 필터링
"""
import os
import sys
import re
from enum import Enum
from typing import Optional
from dataclasses import dataclass

from utils import ConfigManager, logger

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate_json


class LeadIntent(Enum):
    """리드 의도 분류"""
    PURCHASE = "purchase"      # 구매/예약 의도
    INQUIRY = "inquiry"        # 정보 요청
    COMPARISON = "comparison"  # 비교/검토
    REVIEW = "review"          # 후기 공유
    NONE = "none"              # 관련 없음


class LeadPriority(Enum):
    """리드 우선순위"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class ClassificationResult:
    """분류 결과"""
    priority: LeadPriority
    intent: LeadIntent
    confidence: float
    matched_keywords: list
    nlp_used: bool = False
    reject_reason: str = ""  # 제외된 경우 이유


class LeadClassifier:
    """
    잠재 고객 분류기 (v2 - 정밀 필터링)

    규림한의원 타겟:
    - 청주 지역에서 한의원/다이어트/통증치료를 찾는 사람
    - 가격, 예약, 위치 문의하는 사람
    """

    # ===== HIGH: 명확한 구매/예약 의도 =====
    HIGH_KEYWORDS = [
        # 예약 의도
        "예약하고 싶", "예약 가능", "예약하려", "예약 문의",
        "상담 받고 싶", "상담받고싶", "상담 예약",
        # 가격 문의 (구체적)
        "가격이 얼마", "비용이 얼마", "얼마예요", "얼마인가요", "얼마정도",
        "가격 알려", "비용 알려", "가격표",
        # 연락처/위치 (구체적 요청)
        "전화번호 알려", "연락처 알려", "번호 좀", "카톡 주소",
        "주소가 어디", "위치가 어디", "어디에 있어", "찾아가려",
        # 진료 의도
        "진료 받고 싶", "치료 받고 싶", "시술 받고 싶",
        "다니고 싶", "가보고 싶", "방문하고 싶",
    ]

    # ===== MEDIUM: 정보 탐색 (구체적 질문) =====
    MEDIUM_KEYWORDS = [
        # 운영 정보
        "영업시간", "진료시간", "몇시까지", "주말 진료", "일요일 진료",
        "휴무일", "점심시간",
        # 구체적 서비스 문의 (더 구체적으로)
        "다이어트 한약", "한약 다이어트", "살빼는 한약",
        "교통사고 치료", "교통사고 한의원", "자동차보험 한의원",
        "추나 치료", "도침 치료", "침 치료",
        "비만 클리닉", "체형 교정", "턱관절 치료",
        "허리 디스크", "목 디스크", "디스크 치료",  # 더 구체적으로
        # 후기/추천 요청 (더 구체적으로)
        "한의원 추천", "추천해 주세요", "추천좀 해주세요",
        "어디가 좋아요", "어느 한의원이",
        "후기 있나요", "효과 있나요", "효과 봤어요",
        # 비용 관련 (간접)
        "보험 되나요", "실비 되나요", "실비 가능",
    ]

    # ===== LOW: 관심 표현 (더 구체적으로) =====
    LOW_KEYWORDS = [
        "한의원 알아보는 중", "한의원 찾아보는 중",
        "다이어트 고민 중", "치료 생각 중",
        "한의원 관심", "한방 치료 알고 싶",
    ]

    # ===== 제외 패턴 (적극적 필터링) =====
    EXCLUDE_PATTERNS = [
        # 홍보성 댓글/한의원 직원
        r"원장.*입니다",
        r"부원장",
        r"한의원에서.*있을",  # "한의원에서 근무했을 때"
        r"제가.*한의원",  # "제가 XX한의원에서"
        r"상담.*문의",
        r"010-?\d{4}-?\d{4}",
        r"카톡.*[A-Za-z0-9]",
        r"카카오톡.*상담",
        r"DM.*주세요",
        r"프로필.*링크",
        r"채널.*구독",
        r"구독.*좋아요",
        r"팔로우.*해주",
        r"링크.*클릭",
        r"링크.*통해",  # "아래 링크를 통해" 류
        r"http[s]?://",  # URL 포함 댓글
        r"협찬",
        r"광고",
        # 타제품 홍보
        r"저에겐.*잘.*맞더라",  # "저에겐 XX가 잘 맞더라구요"
        r"덕분에.*감량",  # "그 덕분에 감량 성공"
        # 일반 감상/리액션
        r"^(ㅋ|ㅎ|ㅠ|ㅜ)+$",
        r"^(굿|짱|대박|멋져|최고|좋아요)!*$",
        r"^와+!*$",
        r"^오+!*$",
        # 비꼬는/냉소적/리액션 댓글
        r"ㅋㅋ$",  # 끝에 ㅋㅋ로 끝나는 댓글 (비꼬는 톤)
        r"ㅋㅋㅋ",  # 과도한 ㅋ
        r"시대에.*ㅋ",  # "~시대에 ~라니 ㅋ" 패턴
        r"있다뇨",  # 감탄사 "~있다뇨"
        r"헉$",  # 감탄사 "헉"으로 끝나는 댓글
        r"^와.*헉",  # "와... 헉" 류 리액션
        # 영상/컨텐츠 관련 (다이어트 댓스 등)
        r"노래.*(좋|최고|대박)",
        r"춤.*(좋|최고|멋)",
        r"동작.*(좋|예쁘|멋)",
        r"안무.*(좋|예쁘)",
        r"쌤.*(최고|짱|화이팅)",
        r"영상.*(감사|좋아)",
        r"정보.*얻고",  # "정보 얻고 갑니다" 류 - 단순 감사
        r"도움이.*될것같",  # 단순 감상
        r"감사.*드리고",  # 단순 감사 인사
        r"좋습니다.*감사",  # "좋습니다 감사합니다" 류
        r"따라.*할.*수.*있어서.*좋",  # "따라 할 수 있어서 좋습니다"
        r"쉽게.*따라",  # "쉽게 따라할 수 있어서"
        # 제약회사/브랜드 오탐
        r"노보노디스크",  # Novo Nordisk 제약사
        r"노보.*노디스크",
        r"제약회사",
        r"시총",  # 시가총액 - 주식 관련
        # 사고/사건 관련 (교통사고 치료 아님)
        r"사고.*목격",
        r"못.*사시겠",
        r"눈에.*밟",
        r"사망",
        r"숨졌",
        # 부작용/불만 후기 (잠재 고객 아님)
        r"부작용이.*심하",
        r"피부.*뒤[집어]",
        r"나아지지.*않",
        # 다른 업체 언급
        r"(소생|참|경희|동의|자생|자인|우리들)한의원",
        r"(강남|서울|부산|대구|인천).*한의원",
        # 의미없는 댓글
        r"^.{1,8}$",  # 8자 이하
    ]

    # ===== 지역 키워드 (가산점) =====
    LOCAL_KEYWORDS = ["청주", "흥덕", "상당", "서원", "청원", "오창", "오송"]

    # ===== 질문 패턴 (가산점) =====
    QUESTION_PATTERNS = [r"\?$", r"요\?$", r"까요\?*$", r"나요\?*$", r"ㅇㅇ\?$"]

    def __init__(self, use_nlp: bool = True):
        self.use_nlp = use_nlp
        self.config = ConfigManager()

    def _should_exclude(self, text: str) -> tuple[bool, str]:
        """제외 패턴 체크"""
        if not text or len(text.strip()) < 10:
            return True, "too_short"

        text_lower = text.lower()

        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, f"pattern:{pattern[:20]}"

        return False, ""

    def _check_keywords(self, text: str, keywords: list) -> list:
        """키워드 매칭 (대소문자 무시)"""
        matched = []
        for kw in keywords:
            if kw.lower() in text.lower():
                matched.append(kw)
        return matched

    def _is_question(self, text: str) -> bool:
        """질문 형태인지 확인"""
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def _has_local_keyword(self, text: str) -> bool:
        """지역 키워드 포함 여부"""
        for kw in self.LOCAL_KEYWORDS:
            if kw in text:
                return True
        return False

    def _is_false_positive(self, text: str, matched_keywords: list) -> tuple[bool, str]:
        """오탐 체크 - 키워드 매칭됐지만 실제로는 노이즈인 경우"""
        text_lower = text.lower()

        # "디스크" 매칭됐는데 노보노디스크(제약사) 언급인 경우
        if any("디스크" in kw for kw in matched_keywords):
            if "노보" in text_lower or "노디스크" in text_lower:
                return True, "노보노디스크(제약사) 오탐"
            if "시총" in text or "제약" in text or "달러" in text:
                return True, "제약회사 관련 오탐"

        # "다이어트 한약" 매칭됐는데 비꼬는 맥락인 경우
        if any("다이어트" in kw for kw in matched_keywords):
            if "시대에" in text and "ㅋ" in text:
                return True, "비꼬는 맥락"
            if "위고비" in text or "마운자로" in text:
                return True, "GLP-1 비교 맥락 - 비꼬는 톤"

        # 단순 정보 감사 댓글
        if "정보" in text and ("얻고" in text or "감사" in text):
            if not any(kw in text for kw in ["가격", "비용", "예약", "문의"]):
                return True, "단순 감사 댓글"

        return False, ""

    def quick_filter(self, text: str) -> tuple[LeadPriority, list]:
        """1단계: 키워드 기반 필터"""
        if not text:
            return LeadPriority.NONE, []

        # 제외 패턴 체크
        should_exclude, reason = self._should_exclude(text)
        if should_exclude:
            return LeadPriority.NONE, []

        # High priority
        matched = self._check_keywords(text, self.HIGH_KEYWORDS)
        if matched:
            return LeadPriority.HIGH, matched

        # Medium priority
        matched = self._check_keywords(text, self.MEDIUM_KEYWORDS)
        if matched:
            return LeadPriority.MEDIUM, matched

        # Low priority
        matched = self._check_keywords(text, self.LOW_KEYWORDS)
        if matched:
            return LeadPriority.LOW, matched

        return LeadPriority.NONE, []

    def classify(self, text: str) -> ClassificationResult:
        """전체 분류 파이프라인"""
        # 제외 체크
        should_exclude, reason = self._should_exclude(text)
        if should_exclude:
            return ClassificationResult(
                priority=LeadPriority.NONE,
                intent=LeadIntent.NONE,
                confidence=1.0,
                matched_keywords=[],
                reject_reason=reason
            )

        # 키워드 필터
        priority, matched_keywords = self.quick_filter(text)

        if priority == LeadPriority.NONE:
            return ClassificationResult(
                priority=LeadPriority.NONE,
                intent=LeadIntent.NONE,
                confidence=1.0,
                matched_keywords=[],
                reject_reason="no_keyword"
            )

        # 오탐 체크
        is_fp, fp_reason = self._is_false_positive(text, matched_keywords)
        if is_fp:
            return ClassificationResult(
                priority=LeadPriority.NONE,
                intent=LeadIntent.NONE,
                confidence=1.0,
                matched_keywords=matched_keywords,
                reject_reason=f"false_positive:{fp_reason}"
            )

        # 가산점 계산
        confidence = 0.7
        if self._is_question(text):
            confidence += 0.15
        if self._has_local_keyword(text):
            confidence += 0.15
        confidence = min(1.0, confidence)

        # 의도 추정
        intent = LeadIntent.INQUIRY
        if any(kw in text.lower() for kw in ["예약", "가고 싶", "받고 싶"]):
            intent = LeadIntent.PURCHASE
        elif any(kw in text.lower() for kw in ["비교", "vs", "어디가 좋"]):
            intent = LeadIntent.COMPARISON
        elif any(kw in text.lower() for kw in ["다녀왔", "받았는데", "효과 봤"]):
            intent = LeadIntent.REVIEW

        # HIGH만 NLP 사용
        nlp_used = False
        if self.use_nlp and priority == LeadPriority.HIGH:
            nlp_result = self._classify_with_nlp(text)
            if nlp_result:
                intent = nlp_result['intent']
                confidence = nlp_result['confidence']
                nlp_used = True

        return ClassificationResult(
            priority=priority,
            intent=intent,
            confidence=confidence,
            matched_keywords=matched_keywords,
            nlp_used=nlp_used
        )

    def _classify_with_nlp(self, text: str) -> Optional[dict]:
        """NLP 의도 분류"""
        prompt = f"""청주 규림한의원의 잠재 고객 여부를 판단하세요.

댓글: "{text}"

판단 기준:
- purchase: 예약/방문 의사 명확 (예: "예약하고 싶어요", "가격 알려주세요")
- inquiry: 정보 요청 (예: "진료시간이 언제예요?", "다이어트 한약 효과있나요?")
- comparison: 비교 중 (예: "A한의원이랑 어디가 나아요?")
- review: 본인 경험 공유 (예: "여기서 치료받았는데 좋았어요")
- none: 관련없음 (광고, 일반 감상, 다른 지역)

JSON으로 응답: {{"intent": "purchase|inquiry|comparison|review|none", "confidence": 0.0-1.0, "reason": "판단 이유"}}
"""
        try:
            result = ai_generate_json(prompt, temperature=0.3)

            if not result:
                return None

            intent_map = {
                "purchase": LeadIntent.PURCHASE,
                "inquiry": LeadIntent.INQUIRY,
                "comparison": LeadIntent.COMPARISON,
                "review": LeadIntent.REVIEW,
                "none": LeadIntent.NONE
            }

            return {
                'intent': intent_map.get(result.get('intent', 'none'), LeadIntent.NONE),
                'confidence': float(result.get('confidence', 0.5))
            }
        except Exception as e:
            logger.warning(f"NLP 분류 실패: {e}")
            return None

    def get_lead_score(self, result: ClassificationResult) -> int:
        """0-100 점수 계산"""
        if result.priority == LeadPriority.NONE:
            return 0

        base_score = {
            LeadPriority.HIGH: 75,
            LeadPriority.MEDIUM: 45,
            LeadPriority.LOW: 20,
        }

        intent_bonus = {
            LeadIntent.PURCHASE: 25,
            LeadIntent.INQUIRY: 15,
            LeadIntent.COMPARISON: 10,
            LeadIntent.REVIEW: 5,
            LeadIntent.NONE: 0
        }

        score = base_score.get(result.priority, 0)
        score += intent_bonus.get(result.intent, 0)
        score = int(score * result.confidence)

        return min(100, max(0, score))


if __name__ == "__main__":
    classifier = LeadClassifier(use_nlp=False)

    test_comments = [
        # 진짜 리드
        "청주에서 다이어트 한의원 예약하고 싶은데요",
        "가격이 얼마예요? 상담 받고 싶어요",
        "영업시간이 몇시까지예요?",
        "교통사고 치료 받으려면 어떻게 해야하나요?",
        "허리 디스크 치료 잘하는 한의원 어디 있나요?",
        # 가짜 리드 (필터링 대상)
        "노래 동작 넘 좋으네요^^",
        "안녕하세요 민예은 원장입니다",
        "소생한의원 어디점인가요???",
        "ㅋㅋㅋㅋ",
        "좋아요!",
        "구독하고 좋아요 눌러주세요",
        "강남에서 한의원 추천해주세요",
        # 오탐 케이스 (실제 발견된 노이즈)
        "위고비 마운자로 시대에 다이어트 한약이라 ㅋㅋ",  # 비꼬는 톤
        "노보노디스크가 다이어트약으로 시총 6000억 달러",  # 제약사
        "허리 디스크 치료 정보를 많이 얻고갑니다~~",  # 단순 감사
        "아침에 사고 직후 모습 목격했습니다",  # 사건 목격
    ]

    print("=== Lead Classifier v2 Test ===\n")
    for comment in test_comments:
        result = classifier.classify(comment)
        score = classifier.get_lead_score(result)

        status = "PASS" if result.priority != LeadPriority.NONE else "REJECT"
        print(f"[{status}] {comment[:40]}...")
        if status == "PASS":
            print(f"  Score: {score} | Priority: {result.priority.value} | Intent: {result.intent.value}")
            print(f"  Keywords: {result.matched_keywords}")
        else:
            print(f"  Reason: {result.reject_reason}")
        print()
