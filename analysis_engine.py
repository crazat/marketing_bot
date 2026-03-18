import re
import logging
import sqlite3
import os
from collections import Counter

# Configure logging
logger = logging.getLogger("AnalysisEngine")

class AnalysisEngine:
    """
    Component responsible for 'Deep Comparision' between our content and competitors.
    """
    
    def __init__(self):
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'marketing_data.db')

    def analyze_gap(self, our_content_summary, competitor_content_summary):
        """
        Compares two content summaries and returns actionable insights.
        
        Args:
            our_content_summary (dict): {'text_len': 1000, 'img_count': 5, 'keywords': ['diet', 'hanyak']}
            competitor_content_summary (dict): {'text_len': 2000, 'img_count': 12, 'keywords': ['diet', 'event', 'discount']}
            
        Returns:
            dict: Structured gap analysis
        """
        insights = []
        
        # 1. Structural Analysis (Images)
        img_diff = competitor_content_summary.get('img_count', 0) - our_content_summary.get('img_count', 0)
        if img_diff > 3:
            insights.append(f"📸 이미지 부족: 경쟁사가 {img_diff}장 더 많습니다. 시각적 요소를 보강하세요.")
            
        # 2. Text Volume
        len_diff = competitor_content_summary.get('text_len', 0) - our_content_summary.get('text_len', 0)
        if len_diff > 500:
            insights.append(f"📝 분량 부족: 경쟁사 글이 약 {len_diff}자 더 깁니다. 상세 내용을 추가하세요.")
            
        # 3. Keyword Gap
        comp_kws = set(competitor_content_summary.get('keywords', []))
        our_kws = set(our_content_summary.get('keywords', []))
        missing_kws = list(comp_kws - our_kws)
        
        if missing_kws:
            # Filter meaningful ones (mock logic)
            top_missing = missing_kws[:3] 
            insights.append(f"🔑 키워드 누락: 경쟁사는 '{', '.join(top_missing)}' 키워드를 공략 중입니다.")
            
        return {
            "score_gap": -10, # Mock score
            "primary_reason": insights[0] if insights else "비슷한 수준입니다.",
            "detailed_advice": "\n".join(insights)
        }

    def get_connection(self):
        """Returns a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def analyze_rank_drop(self, keyword):
        """
        Real Analysis: Compare latest rank vs previous rank from DB.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get last 2 records
            cursor.execute("SELECT rank, checked_at FROM rank_history WHERE keyword=? ORDER BY id DESC LIMIT 2", (keyword,))
            rows = cursor.fetchall()
            
            if len(rows) < 2:
                return None # Not enough history to analyze drop
                
            latest_rank = rows[0][0]
            prev_rank = rows[1][0]
            
            # Logic: If rank dropped (larger number is worse, or 0 means out)
            # Handle 0 (Out of Rank)
            if latest_rank == 0 and prev_rank > 0:
                return {
                    "status": "DROP_OUT",
                    "gap": -100,
                    "primary_reason": f"순위권 이탈 (기존 {prev_rank}위 -> 0위). 신규 경쟁글 다수 진입 추정."
                }
                
            if latest_rank > prev_rank:
                gap = latest_rank - prev_rank
                return {
                    "status": "DROP",
                    "gap": gap,
                    "primary_reason": f"{gap}단계 하락. (경쟁사 최신성 글에 밀림)"
                }
                
            return None # No drop
        
    def real_scan_and_analyze(self, keyword):
        """
        실제 DB 데이터를 분석하여 우리 콘텐츠와 경쟁사를 비교합니다.
        mentions 테이블에서 최근 30일 데이터를 활용합니다.
        """
        logger.info(f"Real DB analyzing keyword: {keyword}...")
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 1. 우리 콘텐츠 분석 (mentions 테이블에서 '규림' 관련)
            cursor.execute("""
                SELECT 
                    AVG(LENGTH(content)) as avg_len, 
                    COUNT(*) as total,
                    GROUP_CONCAT(DISTINCT keyword) as keywords
                FROM mentions 
                WHERE target_name LIKE '%규림%' 
                AND scraped_at >= date('now', '-30 days')
            """)
            our_row = cursor.fetchone()
            
            our_avg_len = our_row[0] if our_row[0] else 0
            our_total = our_row[1] if our_row[1] else 0
            our_keywords = (our_row[2] or '').split(',') if our_row[2] else []
            
            # 2. 경쟁사 콘텐츠 분석 (동일 키워드 검색)
            cursor.execute("""
                SELECT 
                    AVG(LENGTH(content)) as avg_len, 
                    COUNT(*) as total,
                    GROUP_CONCAT(DISTINCT keyword) as keywords
                FROM mentions 
                WHERE target_name NOT LIKE '%규림%' 
                AND (keyword LIKE ? OR content LIKE ?)
                AND scraped_at >= date('now', '-30 days')
            """, (f'%{keyword}%', f'%{keyword}%'))
            comp_row = cursor.fetchone()
            
            comp_avg_len = comp_row[0] if comp_row[0] else 0
            comp_total = comp_row[1] if comp_row[1] else 0
            comp_keywords = (comp_row[2] or '').split(',') if comp_row[2] else []
            
            conn.close()
            
            # 3. 데이터가 부족한 경우 처리
            if our_total == 0 and comp_total == 0:
                return {
                    "score_gap": 0,
                    "primary_reason": "분석할 데이터가 충분하지 않습니다. 먼저 스크래핑을 실행해주세요.",
                    "detailed_advice": "mentions 테이블에 최근 30일 내 데이터가 없습니다."
                }
            
            # 4. 실제 데이터 기반 gap 분석
            our_data = {
                'text_len': int(our_avg_len),
                'total_posts': our_total,
                'keywords': [kw.strip() for kw in our_keywords if kw.strip()]
            }
            
            competitor_data = {
                'text_len': int(comp_avg_len),
                'total_posts': comp_total,
                'keywords': [kw.strip() for kw in comp_keywords if kw.strip()]
            }
            
            # 5. 콘텐츠 양 비교 분석 추가
            result = self.analyze_gap(our_data, competitor_data)
            
            # 6. 포스팅 빈도 분석 추가
            if comp_total > our_total * 2:
                result["detailed_advice"] += f"\n📊 포스팅 빈도: 경쟁사({comp_total}건) vs 우리({our_total}건). 콘텐츠 생산량 증가 필요."
            
            logger.info(f"Analysis complete - Our: {our_total} posts, Comp: {comp_total} posts")
            return result
            
        except Exception as e:
            logger.error(f"Real analysis failed: {e}")
            return {
                "score_gap": 0,
                "primary_reason": f"분석 중 오류 발생: {e}",
                "detailed_advice": "데이터베이스 연결을 확인해주세요."
            }
