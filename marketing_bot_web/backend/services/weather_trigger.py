"""
날씨 기반 마케팅 트리거
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-1] 기상 조건에 따른 자동 콘텐츠 트리거

기상 조건 → 한의원 마케팅 트리거 매핑:
- 기온 급락 (5°C+ 하강) → 환절기 면역, 감기 예방
- 미세먼지 나쁨 (PM2.5 > 35) → 비염/호흡기 한방치료
- 폭염 (33°C+) → 여름 보양, 더위 한약
- 봄 꽃가루 (3-5월, 기온 10-25°C) → 알레르기 한의원
- 한파 (-10°C 이하) → 겨울 관절, 한방 온열
- 습도 높음 (>80%) → 습열 체질, 부종 관리

필요 설정 (config/config.json):
{
    "openweathermap": {
        "api_key": "...",   // https://openweathermap.org/api 무료 1000건/일
        "city": "Cheongju"  // 기본 도시
    }
}
"""

import os
import sys
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 한의원 날씨 트리거 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WEATHER_TRIGGERS = {
    "cold_snap": {
        "condition": lambda w, prev: prev and (prev["temp"] - w["temp"]) >= 5,
        "name": "기온 급락",
        "icon": "🥶",
        "keywords": ["환절기 한의원", "면역력 한약", "감기 한방치료"],
        "content_themes": [
            "환절기 면역력 강화를 위한 한방 관리법",
            "급격한 기온 변화, 한의원에서 미리 대비하세요",
        ],
        "target_audience": "면역력 약한 분, 어르신, 어린이",
    },
    "fine_dust": {
        "condition": lambda w, prev: w.get("pm25", 0) > 35,
        "name": "미세먼지 나쁨",
        "icon": "😷",
        "keywords": ["비염 한방치료", "미세먼지 한의원", "호흡기 한방"],
        "content_themes": [
            "미세먼지 나쁨! 비염 악화 전 한방 관리법",
            "미세먼지 시즌, 호흡기 건강 한방으로 지키세요",
        ],
        "target_audience": "비염/천식 환자, 호흡기 질환",
    },
    "heat_wave": {
        "condition": lambda w, prev: w["temp"] >= 33,
        "name": "폭염",
        "icon": "🔥",
        "keywords": ["여름 보양 한약", "더위 한의원", "여름 다이어트"],
        "content_themes": [
            "폭염 속 기력 회복, 한방 보양이 답입니다",
            "여름 더위에 지친 몸, 한약으로 활력 충전",
        ],
        "target_audience": "체력 저하, 식욕 부진, 여름철 피로",
    },
    "spring_allergy": {
        "condition": lambda w, prev: (
            3 <= datetime.now().month <= 5
            and 10 <= w["temp"] <= 25
            and w.get("humidity", 50) < 60
        ),
        "name": "봄 알레르기 시즌",
        "icon": "🌸",
        "keywords": ["알레르기 한의원", "봄철 비염", "피부 알레르기 한방"],
        "content_themes": [
            "봄 알레르기 시즌! 비염·피부 한방 관리법",
            "꽃가루 알레르기, 체질 개선으로 근본 해결",
        ],
        "target_audience": "알레르기 비염, 피부 질환",
    },
    "cold_wave": {
        "condition": lambda w, prev: w["temp"] <= -10,
        "name": "한파",
        "icon": "❄️",
        "keywords": ["겨울 관절 한의원", "한방 온열치료", "동절기 건강"],
        "content_themes": [
            "한파 경보! 관절 통증 악화 전 한방 치료",
            "추운 겨울, 한방 온열치료로 관절 건강 지키세요",
        ],
        "target_audience": "관절 질환, 어르신, 냉증",
    },
    "high_humidity": {
        "condition": lambda w, prev: w.get("humidity", 50) > 80,
        "name": "고습도",
        "icon": "💧",
        "keywords": ["습열 체질 한의원", "부종 한방치료", "장마 건강"],
        "content_themes": [
            "높은 습도에 몸이 무거우신가요? 습열 체질 관리법",
            "장마철 부종·소화불량, 한방으로 가볍게",
        ],
        "target_audience": "부종, 소화불량, 습열 체질",
    },
}


async def fetch_current_weather(
    api_key: str,
    city: str = "Cheongju",
    country: str = "KR",
) -> Optional[Dict[str, Any]]:
    """OpenWeatherMap API로 현재 날씨 조회"""
    try:
        import httpx

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": f"{city},{country}",
            "appid": api_key,
            "units": "metric",
            "lang": "kr",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"날씨 API 오류: {response.status_code}")
                return None

            data = response.json()

            return {
                "temp": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "humidity": data["main"]["humidity"],
                "description": data["weather"][0]["description"],
                "wind_speed": data["wind"]["speed"],
                "city": city,
                "fetched_at": datetime.now().isoformat(),
            }

    except ImportError:
        logger.error("httpx 패키지 필요")
        return None
    except Exception as e:
        logger.error(f"날씨 조회 실패: {e}")
        return None


async def fetch_air_quality(
    api_key: str,
    lat: float = 36.6424,
    lon: float = 127.4890,
) -> Optional[Dict[str, float]]:
    """OpenWeatherMap Air Pollution API로 미세먼지 조회"""
    try:
        import httpx

        url = "http://api.openweathermap.org/data/2.5/air_pollution"
        params = {"lat": lat, "lon": lon, "appid": api_key}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code != 200:
                return None

            data = response.json()
            components = data["list"][0]["components"]
            return {
                "pm25": components.get("pm2_5", 0),
                "pm10": components.get("pm10", 0),
                "aqi": data["list"][0]["main"]["aqi"],
            }

    except Exception as e:
        logger.error(f"대기질 조회 실패: {e}")
        return None


def get_previous_weather(db_path: str) -> Optional[Dict[str, Any]]:
    """DB에서 이전 날씨 데이터 조회 (기온 급락 감지용)"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='weather_log'
        """)
        if not cursor.fetchone():
            return None

        cursor.execute("""
            SELECT temp, humidity, fetched_at
            FROM weather_log
            ORDER BY fetched_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None

    except Exception:
        return None
    finally:
        if conn:
            conn.close()


def save_weather_log(db_path: str, weather: Dict[str, Any]):
    """날씨 데이터를 DB에 저장"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temp REAL,
                feels_like REAL,
                humidity INTEGER,
                pm25 REAL DEFAULT 0,
                pm10 REAL DEFAULT 0,
                description TEXT,
                city TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            INSERT INTO weather_log (temp, feels_like, humidity, pm25, pm10, description, city)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            weather.get("temp"),
            weather.get("feels_like"),
            weather.get("humidity"),
            weather.get("pm25", 0),
            weather.get("pm10", 0),
            weather.get("description", ""),
            weather.get("city", ""),
        ))

        conn.commit()
    except Exception as e:
        logger.error(f"날씨 로그 저장 실패: {e}")
    finally:
        if conn:
            conn.close()


def evaluate_triggers(
    weather: Dict[str, Any],
    previous: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """현재 날씨에서 발동되는 트리거 목록 반환"""
    triggered = []

    for trigger_id, trigger in WEATHER_TRIGGERS.items():
        try:
            if trigger["condition"](weather, previous):
                triggered.append({
                    "id": trigger_id,
                    "name": trigger["name"],
                    "icon": trigger["icon"],
                    "keywords": trigger["keywords"],
                    "content_themes": trigger["content_themes"],
                    "target_audience": trigger["target_audience"],
                    "weather_data": {
                        "temp": weather.get("temp"),
                        "humidity": weather.get("humidity"),
                        "pm25": weather.get("pm25"),
                    },
                })
        except Exception as e:
            logger.debug(f"트리거 '{trigger_id}' 평가 실패: {e}")

    return triggered


async def check_weather_triggers(db_path: str) -> Dict[str, Any]:
    """
    메인 함수: 날씨 조회 → 트리거 평가 → 결과 반환

    Returns:
        {weather, air_quality, triggers, timestamp}
    """
    # API 키 로드
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        config_path = os.path.join(project_root, "config", "config.json")

        api_key = ""
        city = "Cheongju"

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                owm = config.get("openweathermap", {})
                api_key = owm.get("api_key", "")
                city = owm.get("city", "Cheongju")

        if not api_key:
            return {
                "error": "OpenWeatherMap API 키가 설정되지 않았습니다.",
                "setup": 'config/config.json에 "openweathermap": {"api_key": "..."} 추가',
            }

    except Exception as e:
        return {"error": f"설정 로드 실패: {e}"}

    # 날씨 + 대기질 조회
    weather = await fetch_current_weather(api_key, city)
    if not weather:
        return {"error": "날씨 데이터 조회 실패"}

    air = await fetch_air_quality(api_key)
    if air:
        weather["pm25"] = air["pm25"]
        weather["pm10"] = air["pm10"]

    # 이전 날씨 조회 (기온 급락 감지용)
    previous = get_previous_weather(db_path)

    # 날씨 로그 저장
    save_weather_log(db_path, weather)

    # 트리거 평가
    triggers = evaluate_triggers(weather, previous)

    result = {
        "weather": weather,
        "air_quality": air,
        "triggers": triggers,
        "trigger_count": len(triggers),
        "timestamp": datetime.now().isoformat(),
    }

    if triggers:
        logger.info(f"🌤️ {len(triggers)}개 날씨 트리거 발동: {[t['name'] for t in triggers]}")

    return result
