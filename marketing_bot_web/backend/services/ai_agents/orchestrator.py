"""
Agent Orchestrator - 에이전트 조율 및 태스크 분배
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-1] 멀티 에이전트 조율기

사용법:
    orchestrator = AgentOrchestrator(db_path="...")
    result = await orchestrator.run("seo", {"action": "analyze_rankings"})
    report = await orchestrator.daily_briefing()
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """에이전트 조율기 - 태스크를 적절한 에이전트에 분배하고 결과를 수집"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path
        self._agents = {}
        self._init_agents()

    def _init_agents(self):
        """에이전트 등록"""
        try:
            from services.ai_agents.seo_agent import SEOAgent
            from services.ai_agents.competitor_agent import CompetitorAgent
            from services.ai_agents.content_agent import ContentAgent

            self._agents = {
                "seo": SEOAgent(db_path=self.db_path),
                "competitor": CompetitorAgent(db_path=self.db_path),
                "content": ContentAgent(db_path=self.db_path),
            }
            logger.info(f"🤖 {len(self._agents)}개 에이전트 초기화 완료")
        except Exception as e:
            logger.error(f"에이전트 초기화 실패: {e}")

        # [고도화 D-1] Naver API 도구 초기화
        try:
            from services.ai_agents.naver_tools import NaverApiTools
            self._naver_tools = NaverApiTools()
            if self._naver_tools.is_configured():
                logger.info("🔗 Naver API 도구 연결 완료")
            else:
                logger.info("🔗 Naver API 도구 대기 (인증 미설정)")
        except Exception as e:
            self._naver_tools = None
            logger.debug(f"Naver API 도구 초기화 스킵: {e}")

    def get_available_agents(self) -> Dict[str, Dict[str, str]]:
        """사용 가능한 에이전트 목록"""
        return {
            name: {"name": agent.name, "role": agent.role, "goal": agent.goal}
            for name, agent in self._agents.items()
        }

    async def run(self, agent_name: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        특정 에이전트에게 태스크 실행 요청

        Args:
            agent_name: 에이전트 키 (seo, competitor, content)
            task: 태스크 딕셔너리 (action 필드 필수)

        Returns:
            에이전트 실행 결과
        """
        if agent_name not in self._agents:
            return {
                "error": f"Unknown agent: {agent_name}",
                "available": list(self._agents.keys()),
            }

        agent = self._agents[agent_name]
        start = datetime.now()

        try:
            logger.info(f"🤖 [{agent.name}] 태스크 실행: {task.get('action', 'unknown')}")
            result = await agent.execute(task)
            elapsed = (datetime.now() - start).total_seconds()

            result["_meta"] = {
                "agent": agent_name,
                "agent_name": agent.name,
                "action": task.get("action", ""),
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.now().isoformat(),
            }
            logger.info(f"🤖 [{agent.name}] 완료 ({elapsed:.1f}s)")
            return result

        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            logger.error(f"🤖 [{agent.name}] 실패: {e}")
            return {
                "error": str(e),
                "_meta": {
                    "agent": agent_name,
                    "elapsed_seconds": round(elapsed, 2),
                    "timestamp": datetime.now().isoformat(),
                }
            }

    async def daily_briefing(self) -> Dict[str, Any]:
        """
        일일 브리핑 - 모든 에이전트의 핵심 분석을 종합

        Returns:
            종합 브리핑 결과 (SEO + 경쟁사 + 콘텐츠)
        """
        results = {}

        # SEO 분석
        results["seo"] = await self.run("seo", {"action": "analyze_rankings"})

        # 경쟁사 분석
        results["competitor"] = await self.run("competitor", {"action": "analyze_competitors"})

        # 콘텐츠 제안
        results["content"] = await self.run("content", {"action": "suggest_topics"})

        return {
            "type": "daily_briefing",
            "sections": results,
            "generated_at": datetime.now().isoformat(),
        }

    async def use_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        [고도화 D-1] Naver API 도구 직접 실행

        Args:
            tool_name: 도구 이름 (search_blog, search_news, get_datalab_trend 등)
            params: 도구 파라미터

        Returns:
            도구 실행 결과
        """
        if not self._naver_tools:
            return {"error": "Naver API 도구가 초기화되지 않았습니다."}

        return await self._naver_tools.execute(tool_name, params)

    def get_available_tools(self) -> Dict[str, Any]:
        """[고도화 D-1] 사용 가능한 Naver API 도구 목록"""
        if not self._naver_tools:
            return {"error": "Naver API 도구 미초기화"}
        return self._naver_tools.get_available_tools()

    async def ask(self, question: str) -> Dict[str, Any]:
        """
        자연어 질문을 적절한 에이전트에 라우팅

        Args:
            question: 사용자 질문

        Returns:
            에이전트 응답
        """
        # 질문 키워드 기반 라우팅
        question_lower = question.lower()

        if any(kw in question_lower for kw in ["순위", "키워드", "seo", "검색", "노출"]):
            agent_name = "seo"
        elif any(kw in question_lower for kw in ["경쟁", "상대", "약점", "기회", "위협"]):
            agent_name = "competitor"
        elif any(kw in question_lower for kw in ["콘텐츠", "블로그", "sns", "인스타", "유튜브", "글"]):
            agent_name = "content"
        else:
            agent_name = "seo"  # 기본값

        agent = self._agents.get(agent_name)
        if not agent:
            return {"error": "에이전트를 찾을 수 없습니다."}

        response = await agent.think(f"""
사용자 질문: {question}

데이터베이스의 마케팅 데이터를 참고하여 실용적이고 구체적인 답변을 제공해주세요.
""", max_tokens=1500)

        return {
            "answer": response,
            "agent": agent_name,
            "agent_name": agent.name,
            "timestamp": datetime.now().isoformat(),
        }
