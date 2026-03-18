"""
Contact Extractor Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[비활성화됨 - 개인정보보호법 준수]

이 서비스는 게시글에서 전화번호, 이메일, 카카오톡 ID 등을 자동으로
추출하도록 설계되었으나, 다음 법적/윤리적 문제로 비활성화되었습니다:

1. 개인정보보호법(PIPA) 제15조: 개인정보 수집 시 정보주체 동의 필수
2. 개인정보보호법 제16조: 수집 목적, 항목, 보유 기간 고지 필수
3. 정보통신망법: 영리 목적 광고성 연락은 사전 동의 필수

게시글에 공개된 연락처라도 마케팅 목적으로 수집/활용 시
법적 제재 대상이 될 수 있습니다.

[호환성 유지]
기존 코드와의 호환성을 위해 extract_contacts() 메서드는 유지되나,
항상 빈 결과를 반환합니다.
"""

import re
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# 개인정보 추출 비활성화 플래그
CONTACT_EXTRACTION_DISABLED = True


class ContactExtractor:
    """
    [비활성화됨] 리드 콘텐츠에서 연락처 정보를 추출하는 클래스

    ⚠️ 주의: 개인정보보호법 준수를 위해 비활성화됨
    - extract_contacts()는 항상 빈 결과 반환
    - 실제 추출 로직은 유지되나 호출되지 않음
    """

    # [개선] 전화번호 패턴 (한국) - 확장
    PHONE_PATTERNS = [
        # 명시적 전화번호 (키워드 + 번호)
        r'(?:전화|연락처|휴대폰|핸드폰|문의|문의처|tel|phone|call|연락)[\s:·\-]*'
        r'(0\d{1,2}[\-\.\s]?\d{3,4}[\-\.\s]?\d{4})',
        # 휴대폰 (010, 011, 016, 017, 019)
        r'(?<!\d)(01[016789][\-\.\s]?\d{3,4}[\-\.\s]?\d{4})(?!\d)',
        # 서울 (02)
        r'(?<!\d)(02[\-\.\s]?\d{3,4}[\-\.\s]?\d{4})(?!\d)',
        # 지역번호 (031~064)
        r'(?<!\d)(0[3-6][0-9][\-\.\s]?\d{3,4}[\-\.\s]?\d{4})(?!\d)',
    ]

    # [개선] 대표번호 패턴 (1588, 1899, 1577 등)
    REPRESENTATIVE_PHONE_PATTERNS = [
        r'(?<!\d)(1[5-9][0-9]{2}[\-\.\s]?\d{4})(?!\d)',  # 15XX-XXXX, 16XX-XXXX 등
    ]

    # [개선] 한글 숫자 변환 매핑
    KOREAN_DIGITS = {
        '영': '0', '공': '0', '빵': '0',
        '일': '1', '하나': '1',
        '이': '2', '둘': '2',
        '삼': '3', '셋': '3',
        '사': '4', '넷': '4',
        '오': '5', '다섯': '5',
        '육': '6', '여섯': '6',
        '칠': '7', '일곱': '7',
        '팔': '8', '여덟': '8',
        '구': '9', '아홉': '9',
    }

    # 이메일 패턴 (개선: 한국 도메인 추가)
    EMAIL_PATTERNS = [
        r'(?:이메일|메일|email|e-mail)[\s:·\-]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|net|org|co\.kr|or\.kr|go\.kr|ac\.kr|ne\.kr|kr))\b',
    ]

    # 카카오톡 ID 패턴 (개선: 오픈채팅 링크 추가)
    KAKAO_PATTERNS = [
        r'(?:카[카톡]?|카카오|kakao|카톡|open\s*chat|오픈챗|오픈채팅)[\s:·\-]*(?:id|아이디|ID)?[\s:·\-]*([a-zA-Z0-9_\-]{3,20})',
        r'(?:카톡[\s]*(?:아이디|id|ID)[\s:·\-]*)([a-zA-Z0-9_\-]{3,20})',
    ]

    # [개선] 카카오 오픈채팅 링크 패턴
    KAKAO_OPENCHAT_PATTERN = r'(open\.kakao\.com/[a-zA-Z0-9/\-_]+)'

    # 인스타그램 ID 패턴
    INSTAGRAM_PATTERNS = [
        r'(?:인스타|insta|instagram|ig)[\s:·\-]*(?:@)?([a-zA-Z0-9_.]{1,30})',
        r'@([a-zA-Z0-9_.]{3,30})(?=\s|$)',  # @username
    ]

    # [개선] 제외할 패턴 (오탐 방지) - 확장
    EXCLUDE_PATTERNS = [
        r'^\d{4}$',                  # 연도만 (2024)
        r'^\d{6}$',                  # 날짜만 (YYMMDD)
        r'^\d{8}$',                  # 날짜만 (YYYYMMDD)
        r'^test',                    # 테스트
        r'^example',                 # 예시
        r'^admin',                   # 관리자
        r'^sample',                  # 샘플
        r'noreply|no-reply',         # 발신전용
    ]

    # [개선] 날짜 패턴 (전화번호 오탐 방지용)
    DATE_PATTERNS = [
        r'20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}',  # 2024.01.01, 2024년 1월 1일
        r'\d{4}[.\-/]\d{2}[.\-/]\d{2}',                    # YYYY.MM.DD
        r'\d{2}[.\-/]\d{2}[.\-/]\d{4}',                    # MM.DD.YYYY
    ]

    # [개선] 제외할 숫자 패턴 (주문번호, 상품코드 등)
    EXCLUDE_NUMBER_CONTEXTS = [
        r'주문번호', r'주문\s*번호', r'order',
        r'상품코드', r'상품\s*코드', r'product',
        r'회원번호', r'회원\s*번호', r'member',
        r'접수번호', r'예약번호', r'결제번호',
    ]

    def extract_contacts(self, text: str) -> Dict[str, Any]:
        """
        [비활성화됨] 텍스트에서 연락처 정보를 추출

        ⚠️ 개인정보보호법 준수를 위해 비활성화됨
        항상 빈 결과를 반환합니다.

        Args:
            text: 분석할 텍스트 (사용되지 않음)

        Returns:
            빈 연락처 정보
        """
        # [비활성화] 개인정보 수집 중단
        if CONTACT_EXTRACTION_DISABLED:
            return {
                'phone': [],
                'email': [],
                'kakao': [],
                'instagram': [],
                'has_contact': False,
                'summary': '',
                '_disabled': True,
                '_reason': '개인정보보호법 준수를 위해 비활성화됨'
            }

        # === 아래 코드는 비활성화됨 (CONTACT_EXTRACTION_DISABLED=False 시에만 실행) ===

        if not text:
            return {
                'phone': [],
                'email': [],
                'kakao': [],
                'instagram': [],
                'has_contact': False,
                'summary': ''
            }

        # 텍스트 정규화 (공백 정리)
        normalized_text = re.sub(r'\s+', ' ', text)

        result = {
            'phone': self._extract_phones(normalized_text),
            'email': self._extract_emails(normalized_text),
            'kakao': self._extract_kakao(normalized_text),
            'instagram': self._extract_instagram(normalized_text),
        }

        # 연락처 존재 여부
        result['has_contact'] = any([
            result['phone'],
            result['email'],
            result['kakao'],
            result['instagram']
        ])

        # 요약 생성
        summary_parts = []
        if result['phone']:
            summary_parts.append(f"전화번호 {len(result['phone'])}개")
        if result['email']:
            summary_parts.append(f"이메일 {len(result['email'])}개")
        if result['kakao']:
            summary_parts.append(f"카카오톡 {len(result['kakao'])}개")
        if result['instagram']:
            summary_parts.append(f"인스타그램 {len(result['instagram'])}개")

        result['summary'] = ', '.join(summary_parts) if summary_parts else '연락처 없음'

        return result

    def _extract_phones(self, text: str) -> List[str]:
        """전화번호 추출 [개선됨]"""
        phones = set()

        # 먼저 날짜 패턴을 마스킹하여 오탐 방지
        masked_text = text
        for date_pattern in self.DATE_PATTERNS:
            masked_text = re.sub(date_pattern, '[DATE]', masked_text)

        # 제외 컨텍스트 주변 숫자 마스킹
        for context in self.EXCLUDE_NUMBER_CONTEXTS:
            # 컨텍스트 뒤에 오는 숫자 패턴 마스킹
            masked_text = re.sub(
                rf'{context}[\s:·\-]*[\d\-\.]+',
                '[EXCLUDED]',
                masked_text,
                flags=re.IGNORECASE
            )

        # 1. 일반 전화번호 패턴
        for pattern in self.PHONE_PATTERNS:
            matches = re.findall(pattern, masked_text, re.IGNORECASE)
            for match in matches:
                formatted = self._format_phone(match)
                if formatted:
                    phones.add(formatted)

        # 2. 대표번호 패턴
        for pattern in self.REPRESENTATIVE_PHONE_PATTERNS:
            matches = re.findall(pattern, masked_text, re.IGNORECASE)
            for match in matches:
                cleaned = re.sub(r'[^\d]', '', match)
                if len(cleaned) == 8:
                    formatted = f"{cleaned[:4]}-{cleaned[4:]}"
                    phones.add(formatted)

        # 3. 한글 전화번호 추출
        korean_phones = self._extract_korean_phones(masked_text)
        phones.update(korean_phones)

        return list(phones)[:5]  # 최대 5개로 확장

    def _format_phone(self, phone_str: str) -> Optional[str]:
        """전화번호 포맷팅"""
        # 숫자만 추출
        cleaned = re.sub(r'[^\d]', '', phone_str)

        # 유효한 전화번호 형식인지 확인
        if len(cleaned) < 9 or len(cleaned) > 12:
            return None

        # 휴대폰 (11자리: 010, 011, 016, 017, 019)
        if len(cleaned) == 11 and cleaned[:3] in ['010', '011', '016', '017', '019']:
            return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"

        # 휴대폰 (10자리: 구형 011, 016 등)
        if len(cleaned) == 10 and cleaned[:3] in ['011', '016', '017', '019']:
            return f"{cleaned[:3]}-{cleaned[3:6]}-{cleaned[6:]}"

        # 서울 (02)
        if len(cleaned) == 10 and cleaned.startswith('02'):
            return f"{cleaned[:2]}-{cleaned[2:6]}-{cleaned[6:]}"
        if len(cleaned) == 9 and cleaned.startswith('02'):
            return f"{cleaned[:2]}-{cleaned[2:5]}-{cleaned[5:]}"

        # 지역번호 (031-064)
        if len(cleaned) == 10 and cleaned[:2] in ['03', '04', '05', '06']:
            return f"{cleaned[:3]}-{cleaned[3:6]}-{cleaned[6:]}"
        if len(cleaned) == 11 and cleaned[:2] in ['03', '04', '05', '06']:
            return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"

        return None

    def _extract_korean_phones(self, text: str) -> List[str]:
        """한글로 표기된 전화번호 추출 [개선]"""
        phones = []

        # 한글 숫자 패턴 (공백 포함)
        korean_digit_pattern = r'[영공빵일이삼사오육칠팔구하나둘셋넷다섯여섯일곱여덟아홉]'
        # 연속된 한글 숫자 찾기 (10-11개)
        pattern = rf'({korean_digit_pattern}[\s]*){10,13}'

        matches = re.findall(pattern, text)
        for match in matches:
            # 한글을 숫자로 변환
            digits = ''
            for char in match:
                if char in self.KOREAN_DIGITS:
                    digits += self.KOREAN_DIGITS[char]
                elif char.isspace():
                    continue

            # 유효한 전화번호인지 확인
            if len(digits) in [10, 11] and digits[:3] in ['010', '011', '016', '017', '019']:
                formatted = self._format_phone(digits)
                if formatted:
                    phones.append(formatted)

        return phones

    def _extract_emails(self, text: str) -> List[str]:
        """이메일 추출"""
        emails = set()

        for pattern in self.EMAIL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # 유효한 이메일인지 간단히 확인
                if '@' in match and '.' in match.split('@')[1]:
                    # 제외 패턴 확인
                    if not any(re.search(exc, match, re.IGNORECASE) for exc in self.EXCLUDE_PATTERNS):
                        emails.add(match.lower())

        return list(emails)[:3]  # 최대 3개

    def _extract_kakao(self, text: str) -> List[str]:
        """카카오톡 ID 및 오픈채팅 링크 추출 [개선됨]"""
        kakao_ids = set()
        openchat_links = set()

        # 1. 카카오톡 ID 패턴
        for pattern in self.KAKAO_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                cleaned = match.strip()
                # 유효한 ID인지 확인 (너무 짧거나 숫자만이면 제외)
                if len(cleaned) >= 3 and not cleaned.isdigit():
                    # 제외 패턴 확인
                    if not any(re.search(exc, cleaned, re.IGNORECASE) for exc in self.EXCLUDE_PATTERNS):
                        kakao_ids.add(cleaned)

        # 2. 오픈채팅 링크 추출 [신규]
        openchat_matches = re.findall(self.KAKAO_OPENCHAT_PATTERN, text, re.IGNORECASE)
        for link in openchat_matches:
            # https:// 추가하여 저장
            full_link = f"https://{link}" if not link.startswith('http') else link
            openchat_links.add(full_link)

        # 오픈채팅 링크와 ID를 합쳐서 반환 (링크 우선)
        result = list(openchat_links) + list(kakao_ids)
        return result[:5]  # 최대 5개로 확장

    def _extract_instagram(self, text: str) -> List[str]:
        """인스타그램 ID 추출"""
        insta_ids = set()

        for pattern in self.INSTAGRAM_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                cleaned = match.strip().lower()
                # 유효한 ID인지 확인
                if len(cleaned) >= 3 and len(cleaned) <= 30:
                    # 제외 패턴 확인
                    if not any(re.search(exc, cleaned, re.IGNORECASE) for exc in self.EXCLUDE_PATTERNS):
                        insta_ids.add(cleaned)

        return list(insta_ids)[:3]  # 최대 3개

    def format_contact_info(self, contacts: Dict[str, Any]) -> str:
        """
        추출된 연락처를 저장용 문자열로 포맷

        Returns:
            "전화: 010-1234-5678 | 카톡: example_id"
        """
        parts = []

        if contacts.get('phone'):
            parts.append(f"전화: {', '.join(contacts['phone'])}")
        if contacts.get('email'):
            parts.append(f"이메일: {', '.join(contacts['email'])}")
        if contacts.get('kakao'):
            parts.append(f"카톡: {', '.join(contacts['kakao'])}")
        if contacts.get('instagram'):
            parts.append(f"인스타: {', '.join(contacts['instagram'])}")

        return ' | '.join(parts)


# 싱글톤 인스턴스
_extractor_instance = None


def get_contact_extractor() -> ContactExtractor:
    """ContactExtractor 싱글톤 인스턴스 반환"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = ContactExtractor()
    return _extractor_instance
