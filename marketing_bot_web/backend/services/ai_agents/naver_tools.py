"""
Naver API Tools for AI Agents
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-1] AI 에이전트가 사용할 수 있는 Naver API 도구

MCP(Model Context Protocol) 패턴 구현:
- 에이전트가 도구를 선언적으로 사용
- 각 도구는 입력/출력 스키마가 명확
- 실제 Naver API 호출을 래핑

도구 목록:
1. search_blog: 네이버 블로그 검색
2. search_news: 네이버 뉴스 검색
3. search_kin: 네이버 지식인 검색
4. search_local: 네이버 지역 검색
5. get_datalab_trend: DataLab 트렌드 조회
6. get_keyword_volume: 키워드 검색량 조회 (광고 API)
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NaverApiTools:
    """
    AI 에이전트용 Naver API 도구 모음

    Usage:
        tools = NaverApiTools()
        result = await tools.execute("search_blog", {"query": "청주 한의원"})
    """

    TOOL_DEFINITIONS = {
        "search_blog": {
            "description": "네이버 블로그 검색. 키워드 관련 블로그 포스팅을 찾습니다.",
            "parameters": {
                "query": {"type": "string", "required": True, "description": "검색어"},
                "display": {"type": "integer", "default": 10, "description": "결과 수 (1-100)"},
                "sort": {"type": "string", "default": "sim", "description": "정렬 (sim: 정확도, date: 날짜)"},
            },
        },
        "search_news": {
            "description": "네이버 뉴스 검색. 키워드 관련 뉴스 기사를 찾습니다.",
            "parameters": {
                "query": {"type": "string", "required": True},
                "display": {"type": "integer", "default": 10},
                "sort": {"type": "string", "default": "date"},
            },
        },
        "search_kin": {
            "description": "네이버 지식인 검색. 키워드 관련 질문/답변을 찾습니다.",
            "parameters": {
                "query": {"type": "string", "required": True},
                "display": {"type": "integer", "default": 10},
            },
        },
        "search_local": {
            "description": "네이버 지역 검색. 장소/업체를 검색합니다.",
            "parameters": {
                "query": {"type": "string", "required": True},
                "display": {"type": "integer", "default": 5},
            },
        },
        "get_datalab_trend": {
            "description": "네이버 DataLab 검색어 트렌드. 키워드의 검색 추이를 조회합니다.",
            "parameters": {
                "keywords": {"type": "array", "required": True, "description": "키워드 목록 (최대 5개)"},
                "period": {"type": "integer", "default": 30, "description": "기간 (일)"},
            },
        },
    }

    def __init__(self):
        self._client_id = None
        self._client_secret = None
        self._load_credentials()

    def _load_credentials(self):
        """Naver API 인증 정보 로드"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
            config_path = os.path.join(project_root, "config", "config.json")

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    naver = data.get("naver_api", data.get("naver", {}))
                    self._client_id = naver.get("client_id", "")
                    self._client_secret = naver.get("client_secret", "")
        except Exception as e:
            logger.error(f"Naver API 인증 정보 로드 실패: {e}")

    def get_available_tools(self) -> Dict[str, Any]:
        """사용 가능한 도구 목록 반환"""
        return {
            name: {
                "description": info["description"],
                "parameters": info["parameters"],
                "available": self.is_configured(),
            }
            for name, info in self.TOOL_DEFINITIONS.items()
        }

    def is_configured(self) -> bool:
        """API 인증 정보 설정 여부"""
        return bool(self._client_id and self._client_secret)

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        도구 실행

        Args:
            tool_name: 도구 이름 (search_blog, search_news 등)
            params: 도구 파라미터

        Returns:
            도구 실행 결과
        """
        if tool_name not in self.TOOL_DEFINITIONS:
            return {"error": f"Unknown tool: {tool_name}", "available": list(self.TOOL_DEFINITIONS.keys())}

        if not self.is_configured():
            return {
                "error": "Naver API 인증 정보가 설정되지 않았습니다.",
                "setup": "config/config.json에 naver_api.client_id와 client_secret을 설정하세요.",
            }

        dispatch = {
            "search_blog": self._search,
            "search_news": self._search,
            "search_kin": self._search,
            "search_local": self._search,
            "get_datalab_trend": self._get_datalab_trend,
        }

        handler = dispatch.get(tool_name)
        if not handler:
            return {"error": f"Handler not implemented for: {tool_name}"}

        # search 계열은 endpoint를 tool_name에서 추출
        if tool_name.startswith("search_"):
            endpoint = tool_name.replace("search_", "")
            return await handler(endpoint, params)
        else:
            return await handler(params)

    async def _search(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """네이버 검색 API 호출"""
        try:
            import httpx

            query = params.get("query", "")
            display = min(params.get("display", 10), 100)
            sort = params.get("sort", "sim")

            # endpoint 매핑
            api_map = {
                "blog": "blog.json",
                "news": "news.json",
                "kin": "kin.json",
                "local": "local.json",
            }

            api_endpoint = api_map.get(endpoint, f"{endpoint}.json")
            url = f"https://openapi.naver.com/v1/search/{api_endpoint}"

            headers = {
                "X-Naver-Client-Id": self._client_id,
                "X-Naver-Client-Secret": self._client_secret,
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"query": query, "display": display, "sort": sort},
                    timeout=15.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "total": data.get("total", 0),
                        "items": data.get("items", []),
                        "query": query,
                    }
                else:
                    return {"error": f"API 오류: {response.status_code}", "detail": response.text}

        except ImportError:
            return {"error": "httpx 패키지 필요"}
        except Exception as e:
            return {"error": str(e)}

    async def _get_datalab_trend(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """네이버 DataLab 트렌드 API 호출"""
        try:
            import httpx

            keywords = params.get("keywords", [])
            period = params.get("period", 30)

            if not keywords:
                return {"error": "keywords 파라미터가 필요합니다."}

            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=period)).strftime("%Y-%m-%d")

            url = "https://openapi.naver.com/v1/datalab/search"
            headers = {
                "X-Naver-Client-Id": self._client_id,
                "X-Naver-Client-Secret": self._client_secret,
                "Content-Type": "application/json",
            }

            body = {
                "startDate": start_date,
                "endDate": end_date,
                "timeUnit": "date",
                "keywordGroups": [
                    {"groupName": kw, "keywords": [kw]}
                    for kw in keywords[:5]  # 최대 5개
                ],
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=15.0,
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"DataLab API 오류: {response.status_code}"}

        except Exception as e:
            return {"error": str(e)}
