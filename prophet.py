
import json
import random
import os
from datetime import datetime, timedelta
import re
import requests
from utils import logger, ConfigManager

class TheProphet:
    """
    Real-time Trend Predictor.
    Combines:
    1. Static Seasonal Intelligence (Base)
    2. Dynamic Weather Triggers (Variable) - *Requires external input or manual trigger in this demo*
    3. Simulated Trend Momentum (Datalab Logic)
    """
    def __init__(self):
        self.year = datetime.now().year
        self.config = ConfigManager()

    def _fetch_real_weather(self):
        """
        Scrapes Naver Weather for Cheongju.
        Returns: {temp: int, condition: str, dust: str}
        """
        from selenium.webdriver.common.by import By
        from retry_helper import SafeSeleniumDriver
        import time

        logger.info("Prophet: Checking Real Weather Data for Cheongju...")
        driver = None

        try:
             # Use SafeContext Manager for cleanup
             with SafeSeleniumDriver(headless=True, mobile=False, timeout=20) as driver:
                 url = "https://search.naver.com/search.naver?query=%EC%B2%AD%EC%A3%BC+%EB%82%A0%EC%94%A8" # Cheongju Weather
                 driver.get(url)
                 time.sleep(2)
                 
                 # Extract Temp
                 temp_el = driver.find_element(By.CSS_SELECTOR, ".temperature_text")
                 temp_text = temp_el.text # "현재 온도 5.2°"
                 temp_val = float(re.findall(r"[-+]?\d*\.\d+|\d+", temp_text)[0])
                 
                 # Extract Condition
                 cond_el = driver.find_element(By.CSS_SELECTOR, ".weather_main")
                 condition = cond_el.text
                 
                 # Extract Dust/Air Quality (미세먼지)
                 dust_level = "unknown"
                 try:
                     # 미세먼지 정보는 보통 .today_chart_list 또는 .air 클래스에 있음
                     dust_elements = driver.find_elements(By.CSS_SELECTOR, ".today_chart_list li, .air_quality, .sub_info")
                     for el in dust_elements:
                         text = el.text
                         if "미세먼지" in text or "초미세먼지" in text:
                             if "매우나쁨" in text or "매우 나쁨" in text:
                                 dust_level = "very_bad"
                             elif "나쁨" in text:
                                 dust_level = "bad"
                             elif "보통" in text:
                                 dust_level = "normal"
                             elif "좋음" in text:
                                 dust_level = "good"
                             break
                 except Exception as dust_err:
                     logger.warning(f"Dust data extraction failed: {dust_err}")
                 
                 return {"temp": temp_val, "condition": condition, "dust": dust_level}
                 
        except Exception as e:
            logger.error(f"Weather Scrape Failed: {e}", exc_info=True)
            return None

    def _get_weather_impact(self):
        """
        Analyzes weather forecast impact based on REAL data.
        """
        weather = self._fetch_real_weather()
        if not weather: 
            return [] # No data, no fake alert.
            
        impacts = []
        temp = weather['temp']
        cond = weather['condition']
        
        # Logic: Rainfall/Snow -> Traffic Accidents
        if "비" in cond or "눈" in cond:
            impacts.append({
                "condition": f"{cond} (기온 {temp}°C)",
                "impact_keyword": "청주 교통사고 한의원",
                "reason": "빗길/눈길 미끄럼 사고 급증 예상",
                "action": "ad_bid_increase"
            })
            
        # Logic: Low Temp -> Traffic (Ice) or Dry Skin
        if temp < -5:
             impacts.append({
                "condition": f"한파 ({temp}°C)",
                "impact_keyword": "청주 자동차보험",
                "reason": "도로 결빙 블랙아이스 위험",
                "action": "ad_bid_increase"
             })
             
        # Logic: Dry/Cold -> Skin
        if temp < 5 and "비" not in cond:
             # Assume dry if cold and not raining
             impacts.append({
                "condition": f"건조/추위 ({temp}°C)",
                "impact_keyword": "청주 율량동 건선/아토피",
                "reason": "난방 가동으로 인한 피부 가려움증 호소",
                "action": "content_creation"
             })
        
        # Logic: Dust/Air Quality -> Respiratory Issues
        dust = weather.get('dust', 'unknown')
        if dust in ['bad', 'very_bad']:
            dust_label = "미세먼지 나쁨" if dust == "bad" else "미세먼지 매우나쁨"
            impacts.append({
                "condition": f"{dust_label} (기온 {temp}°C)",
                "impact_keyword": "청주 비염 한의원",
                "reason": "미세먼지로 인한 호흡기/비염 환자 증가 예상",
                "action": "ad_bid_increase"
            })
            impacts.append({
                "condition": f"{dust_label}",
                "impact_keyword": "청주 피부트러블",
                "reason": "대기오염으로 인한 피부 트러블 환자 증가",
                "action": "content_creation"
            })
            # 미세먼지 심할 때 면역력 관련 키워드도 추가
            if dust == "very_bad":
                impacts.append({
                    "condition": f"{dust_label} - 면역력 저하 주의",
                    "impact_keyword": "청주 면역력 한약",
                    "reason": "대기질 악화로 인한 면역력 관리 수요 증가",
                    "action": "content_creation"
                })
             
        return impacts

    def predict_next_week(self):
        """
        Generates a realistic forecast.
        """
        logger.info("🔮 The Prophet: Analyzing Real-time Signals...")
        
        today = datetime.now()
        next_week = today + timedelta(days=7)
        target_period_str = f"{next_week.strftime('%Y-%m-%d')} 주간"
        
        # 1. Base Seasonal Trends (Diversified DB)
        # Using a more granular database than week-by-week
        # 1. Base Seasonal Trends (Diversified DB from JSON)
        try:
            matrix_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'trend_matrix.json')
            with open(matrix_path, 'r', encoding='utf-8') as f:
                trend_matrix = json.load(f)
            
            # trend_matrix keys are strings "1", "2"... convert to str(month)
            month_str = str(today.month)
            month_data = trend_matrix.get(month_str, {})
            
            # Flatten the categories into a list of trends
            current_trends = []
            if month_data:
                # categories: diet, pain, skin, women_kids, general
                for cat, keywords in month_data.items():
                    for kw in keywords:
                        current_trends.append({
                            "kw": kw,
                            "growth": "Seasonal", 
                            "evidence": f"{today.month}월 주요 키워드 ({cat.upper()})",
                            "category": cat
                        })
            
        except Exception as e:
            logger.error(f"Failed to load trend_matrix.json: {e}")
            current_trends = []

        # 2. Weather Triggers (Dynamic)
        weather_impacts = self._get_weather_impact()
        
        forecast = {
            "target_period": target_period_str,
            "rising_trends": []
        }
        
        # Merge & Format
        
        # Add Weather Driven (High Priority)
        for w in weather_impacts:
            forecast["rising_trends"].append({
                "keyword": w['impact_keyword'],
                "predicted_growth": "🚨 급상승 (Weather)",
                "evidence": f"기상청 예보: {w['condition']} → {w['reason']}",
                "action": w['action'],
                "recommended_title": f"[날씨특보] {w['condition']} 주의보, {w['impact_keyword'].split()[-1]} 관리법"
            })
            
        # Add Seasonal
        for t in current_trends:
            # GROWTH PREDICTION (Real Data via Naver Datalab)
            # Fetch real trend data if API available, else fallback to month-based heuristic (marked as Simulated)
            
            trend_slope = self._fetch_datalab_trend(t['kw'])
            is_simulated = False
            
            if trend_slope is None:
                # Fallback to heuristic
                is_simulated = True
                day = today.day
                if day <= 10: growth_tag = "📈 상승세 (Simulated)"
                elif day <= 20: growth_tag = "🔥 정점 (Simulated)"
                else: growth_tag = "📉 하락세 (Simulated)"
            else:
                # Real data logic: slope > 0 means growing
                if trend_slope > 0.5: growth_tag = "🔥 급상승 (Real Data)"
                elif trend_slope > 0: growth_tag = "📈 상승세 (Real Data)"
                elif trend_slope > -0.5: growth_tag = "➡️ 보합세 (Real Data)"
                else: growth_tag = "📉 하락세 (Real Data)"
            
            forecast["rising_trends"].append({
                "keyword": f"청주 {t['kw']}",
                "predicted_growth": growth_tag,
                "evidence": t['evidence'] + (f" (Trend Slope: {trend_slope:.2f})" if trend_slope is not None else ""), 
                "action": "content_preloading",
                "recommended_title": f"{t['kw']}, 남들보다 1주일 먼저 준비하세요."
            })
            
        return forecast

    def _fetch_datalab_trend(self, keyword):
        """
        Fetches Naver Datalab Search Trend for the last 30 days.
        Returns slope of the trend line (float) or None if API fails.
        """
        
        client_id = self.config.get_api_key("NAVER_CLIENT_ID")
        client_secret = self.config.get_api_key("NAVER_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            return None
            
        try:
            url = "https://openapi.naver.com/v1/datalab/search"
            headers = {
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json"
            }
            
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            body = {
                "startDate": start_date,
                "endDate": end_date,
                "timeUnit": "date",
                "keywordGroups": [
                    {"groupName": keyword, "keywords": [keyword, f"청주 {keyword}"]}
                ]
            }
            
            response = requests.post(url, headers=headers, json=body, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Parse results
            results = data.get('results', [])
            if not results: return None
            
            metrics = results[0].get('data', [])
            if len(metrics) < 2: return 0.0 # Not enough data
            
            # Simple Linear Regression Logic (slope)
            # x = [0, 1, 2...], y = [ratios]
            n = len(metrics)
            xs = range(n)
            ys = [float(m['ratio']) for m in metrics]
            
            # Slope formula: (n*sum(xy) - sum(x)*sum(y)) / (n*sum(x^2) - sum(x)^2)
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xy = sum(x*y for x,y in zip(xs, ys))
            sum_xx = sum(x*x for x in xs)
            
            if (n * sum_xx - sum_x * sum_x) == 0: return 0.0
            
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            return slope
            
        except requests.exceptions.HTTPError as http_err:
            if response.status_code == 401:
                logger.warning(f"Naver Datalab API Unauthorized (401). Please check NAVER_CLIENT_ID/SECRET in secrets.json.")
                return None
            else:
                logger.warning(f"Datalab API HTTP Error for {keyword}: {http_err}")
                return None
        except Exception as e:
            logger.warning(f"Datalab API Failed for {keyword}: {e}")
            return None

if __name__ == "__main__":
    p = TheProphet()
    print(json.dumps(p.predict_next_week(), indent=2, ensure_ascii=False))
