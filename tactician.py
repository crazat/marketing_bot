
import sqlite3
import json
import logging
import random
from datetime import datetime
from utils import ConfigManager

logger = logging.getLogger("Tactician")

class TargetedTactician:
    """
    Component for analyzing competitor reviews (VoC) and generating strategies.
    "Attack the weakness."
    """
    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def fetch_real_reviews(self, competitor_name):
        """
        Fetches REAL reviews from DB (populated by scraper).
        No more mocks.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Fetch reviews collected in the last 7 days
            cursor.execute(
                "SELECT content, sentiment FROM competitor_reviews WHERE competitor_name=? AND source='naver_place_real' ORDER BY id DESC LIMIT 50",
                (competitor_name,)
            )
            rows = cursor.fetchall()
            
            reviews = []
            for r in rows:
                reviews.append({"content": r[0], "sentiment": r[1]})
                
            return reviews

    def analyze_and_propose(self, competitor_name):
        """
        Main logic: Analyze DB-resident REAL reviews -> Propose Strategy.
        [UPGRADED] Uses AI analysis with keyword fallback.
        """
        # 1. Fetch Real Data from DB
        reviews = self.fetch_real_reviews(competitor_name)
        
        if not reviews:
            return None # No data, no fake strategy.
        
        # 2. Try AI Analysis first, fallback to keyword
        analysis = self._analyze_weakness_ai(reviews, competitor_name)
        
        if not analysis:
            # Fallback to keyword analysis
            analysis = self._fallback_keyword_analysis(reviews, competitor_name)
        
        return analysis
    
    def _analyze_weakness_ai(self, reviews, competitor_name):
        """
        [AI-POWERED] Use Gemini to analyze reviews for nuanced weakness detection.
        More accurate than simple keyword matching.
        """
        from google import genai

        try:
            api_key = self.config.get_api_key()
            if not api_key:
                logger.warning("No API key for AI analysis, using fallback")
                return None

            client = genai.Client(api_key=api_key)
            model_name = 'gemini-3-flash-preview'

            # Build review text (limit to avoid token overflow)
            review_text = "\n".join([f"- {r['content'][:100]}" for r in reviews[:20]])

            prompt = f"""
다음은 '{competitor_name}' 병원/한의원에 대한 실제 고객 리뷰입니다.

[리뷰 목록]
{review_text}

이 리뷰들을 분석하여 가장 큰 약점(불만 사항)을 찾으세요.

다음 JSON 형식으로만 응답하세요:
{{
  "weakness_type": "waiting|price|service|facility|effect|none",
  "complaint_count": 숫자,
  "key_phrases": ["실제 불만 표현 1", "실제 불만 표현 2"],
  "confidence": 0.0~1.0
}}

JSON만 출력하세요.
"""

            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            result_text = response.text.strip()
            
            # Parse JSON
            import re
            json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                
                if analysis.get('weakness_type') == 'none' or analysis.get('confidence', 0) < 0.5:
                    return None
                
                return self._generate_strategy_from_analysis(competitor_name, analysis)
            
            return None
            
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}, using fallback")
            return None
    
    def _generate_strategy_from_analysis(self, competitor_name, analysis):
        """Generate strategy proposal from AI analysis result"""
        weakness_type = analysis.get('weakness_type', 'none')
        count = analysis.get('complaint_count', 0)
        phrases = analysis.get('key_phrases', [])
        
        if count < 2:
            return None
        
        strategy_templates = {
            'waiting': {
                'title': f"⚔️ [{competitor_name}] 대기시간 약점 공략 보고서 (AI분석)",
                'issue': '대기시간/지연',
                'opportunity': "'빠른 진료'를 원하는 환자층을 뺏어올 절호의 기회"
            },
            'price': {
                'title': f"⚔️ [{competitor_name}] 가격 저항선 돌파 전략 (AI분석)",
                'issue': '가격/비용',
                'opportunity': "'가격 대비 가치(Value)' 전략으로 이탈 고객 유인"
            },
            'service': {
                'title': f"⚔️ [{competitor_name}] 서비스 약점 공략 보고서 (AI분석)",
                'issue': '서비스/친절도',
                'opportunity': "'친절한 진료'를 원하는 환자층을 유인할 기회"
            },
            'facility': {
                'title': f"⚔️ [{competitor_name}] 시설 불만 공략 보고서 (AI분석)",
                'issue': '시설/청결도',
                'opportunity': "'깨끗한 환경'을 중시하는 환자 유치 기회"
            },
            'effect': {
                'title': f"⚔️ [{competitor_name}] 효과 불만 공략 보고서 (AI분석)",
                'issue': '치료 효과',
                'opportunity': "전문성과 실력을 강조한 마케팅 기회"
            }
        }
        
        template = strategy_templates.get(weakness_type)
        if not template:
            return None
        
        phrases_text = ', '.join(phrases[:3]) if phrases else 'N/A'
        
        return {
            "title": template['title'],
            "content": f"**[AI 분석 결과]**\n"
                       f"경쟁사 '{competitor_name}' 리뷰에서 '{template['issue']}' 불만이 {count}건 감지되었습니다.\n"
                       f"주요 표현: {phrases_text}\n\n"
                       f"**[기회 분석]**\n{template['opportunity']}\n\n"
                       f"**[제안]** 상세 대응 전략 보고서를 생성하시겠습니까?",
            "suggested_action": "strategy_report",
            "args": f"{competitor_name} {template['issue']} 약점 대응 전략",
            "priority": "high",
            "source": "ai_analysis"
        }
    
    def _fallback_keyword_analysis(self, reviews, competitor_name):
        """
        [FALLBACK] Simple keyword-based analysis when AI is unavailable.
        """
        kw_counter = {}
        
        for r in reviews:
            text = r['content']
            if "대기" in text or "기다" in text:
                kw_counter["waiting_issue"] = kw_counter.get("waiting_issue", 0) + 1
            if "비싸" in text or "가격" in text or "비용" in text:
                kw_counter["price_issue"] = kw_counter.get("price_issue", 0) + 1
            if "불친절" in text or "태도" in text:
                kw_counter["service_issue"] = kw_counter.get("service_issue", 0) + 1
        
        if not kw_counter:
            return None
            
        top_weakness = max(kw_counter, key=kw_counter.get)
        count = kw_counter[top_weakness]
        
        if count < 2:
            return None
        
        strategy_map = {
            "waiting_issue": ("대기시간 약점", "'빠른 진료'를 원하는 환자층 공략"),
            "price_issue": ("가격 저항선", "'가격 대비 가치' 전략"),
            "service_issue": ("서비스 약점", "'친절한 진료' 차별화")
        }
        
        issue, opportunity = strategy_map.get(top_weakness, ("기타", "기타"))
        
        return {
            "title": f"⚔️ [{competitor_name}] {issue} 공략 보고서 (키워드분석)",
            "content": f"**[정보감시 결과]**\n"
                       f"경쟁사 '{competitor_name}' 리뷰에서 관련 불만이 {count}건 포착되었습니다.\n"
                       f"**[기회]** {opportunity}\n\n"
                       f"**[제안]** 상세 대응 전략 보고서를 생성하시겠습니까?",
            "suggested_action": "strategy_report",
            "args": f"{competitor_name} {issue} 대응 전략",
            "priority": "high",
            "source": "keyword_fallback"
        }

if __name__ == "__main__":
    t = TargetedTactician()
    print("Tactician Initialized.")
    # Test
    res = t.analyze_and_propose("데이릴 한의원")
    print(f"Proposed Strategy: {res}")
