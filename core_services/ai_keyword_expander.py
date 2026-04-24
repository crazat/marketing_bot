#!/usr/bin/env python3
"""
AI 기반 키워드 확장 (Gemini)
- 시맨틱 유사 키워드 생성
- 질문형 키워드 생성
- 롱테일 변형 생성
"""

import json
import os
import sys
import re
from typing import List, Dict, Optional
from datetime import datetime

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'marketing_bot_web', 'backend'))

from services.ai_client import ai_generate, ai_generate_json


class AIKeywordExpander:
    """AI 기반 키워드 확장"""

    def __init__(self):
        self.ai_available = True
        print("AI 키워드 확장기 초기화 완료 (centralized ai_client)")

    def is_available(self) -> bool:
        """AI 확장 사용 가능 여부"""
        return self.ai_available

    def expand_semantic(self, seed_keywords: List[str], category: str = "일반",
                        max_results: int = 20) -> List[str]:
        """
        시맨틱 유사 키워드 생성

        Args:
            seed_keywords: 시드 키워드 목록 (최대 10개 사용)
            category: 카테고리
            max_results: 최대 결과 수

        Returns:
            생성된 키워드 목록
        """
        # 시드 키워드 제한
        seeds = seed_keywords[:10]

        prompt = f"""당신은 한의원 마케팅 키워드 전문가입니다.

카테고리: {category}
시드 키워드: {', '.join(seeds)}

위 키워드들과 의미적으로 관련있지만 다른 표현의 키워드를 {max_results}개 생성해주세요.

규칙:
1. "청주" 지역 키워드를 포함 (예: "청주 다이어트 한약")
2. 검색 가능한 자연스러운 표현
3. 구매/예약 의도가 있는 키워드 우선 (가격, 후기, 추천 등)
4. 중복 없이 다양하게
5. 실제 사용자가 검색할 법한 키워드
6. 한의원, 한방, 한약 관련 키워드 포함

JSON 배열로만 응답: ["키워드1", "키워드2", ...]"""

        try:
            text = ai_generate(prompt, temperature=0.7, max_tokens=4096)

            # JSON 추출
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                keywords = json.loads(match.group())
                return [kw for kw in keywords if isinstance(kw, str) and len(kw) > 2]
            return []

        except Exception as e:
            print(f"   AI 시맨틱 확장 실패: {e}")
            return []

    def generate_questions(self, topic: str, region: str = "청주",
                          max_results: int = 15) -> List[str]:
        """
        질문형 키워드 생성 (AnswerThePublic 스타일)

        Args:
            topic: 주제 (예: "다이어트 한약")
            region: 지역
            max_results: 최대 결과 수

        Returns:
            질문형 키워드 목록
        """
        prompt = f"""당신은 검색 키워드 전문가입니다.

주제: {region} {topic}

사용자들이 검색할 수 있는 질문형 키워드를 {max_results}개 생성해주세요.

형식 예시:
- "{region} {topic} 효과 있나요"
- "{region} {topic} 가격 얼마인가요"
- "{region} {topic} 추천해주세요"

규칙:
1. 자연스러운 질문 형식
2. 실제 검색할 법한 표현
3. 다양한 의도 (정보, 비교, 구매)
4. 지역명({region}) 포함

JSON 배열로만 응답: ["질문1", "질문2", ...]"""

        try:
            text = ai_generate(prompt, temperature=0.7, max_tokens=4096)

            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                keywords = json.loads(match.group())
                return [kw for kw in keywords if isinstance(kw, str)]
            return []

        except Exception as e:
            print(f"   AI 질문 생성 실패: {e}")
            return []

    def generate_longtail(self, base_keyword: str, max_results: int = 10) -> List[str]:
        """
        롱테일 변형 생성

        Args:
            base_keyword: 기본 키워드
            max_results: 최대 결과 수

        Returns:
            롱테일 키워드 목록
        """
        prompt = f"""당신은 검색 키워드 전문가입니다.

기본 키워드: {base_keyword}

이 키워드의 롱테일 변형을 {max_results}개 생성해주세요.

롱테일이란: 더 구체적이고 긴 검색어
예시: "다이어트" → "30대 직장인 다이어트 한약 추천"

규칙:
1. 구체적인 상황/대상 추가 (연령, 직업, 시기 등)
2. 구매 의도 키워드 추가 (가격, 후기, 비용 등)
3. 증상/목적 구체화
4. 자연스러운 검색어

JSON 배열로만 응답: ["롱테일1", "롱테일2", ...]"""

        try:
            text = ai_generate(prompt, temperature=0.7, max_tokens=4096)

            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                keywords = json.loads(match.group())
                return [kw for kw in keywords if isinstance(kw, str)]
            return []

        except Exception as e:
            print(f"   AI 롱테일 생성 실패: {e}")
            return []

    def batch_expand(self, categories: Dict[str, List[str]],
                     max_per_category: int = 15) -> Dict[str, List[str]]:
        """
        카테고리별 배치 확장

        Args:
            categories: {카테고리: [시드키워드들]}
            max_per_category: 카테고리당 최대 결과 수

        Returns:
            {카테고리: [확장된 키워드들]}
        """
        results = {}
        for category, seeds in categories.items():
            expanded = self.expand_semantic(seeds, category, max_per_category)
            if expanded:
                results[category] = expanded
                print(f"   🤖 {category}: +{len(expanded)}개 AI 확장")

        return results


# 테스트 코드
if __name__ == '__main__':
    expander = AIKeywordExpander()

    if expander.is_available():
        # 시맨틱 확장 테스트
        seeds = ["청주 다이어트 한의원", "청주 다이어트 한약"]
        expanded = expander.expand_semantic(seeds, "다이어트", max_results=10)
        print(f"시맨틱 확장: {expanded}")

        # 질문형 키워드 테스트
        questions = expander.generate_questions("다이어트 한약", "청주", max_results=5)
        print(f"질문형: {questions}")

        # 롱테일 테스트
        longtail = expander.generate_longtail("청주 다이어트 한의원", max_results=5)
        print(f"롱테일: {longtail}")
    else:
        print("AI 확장 사용 불가")
