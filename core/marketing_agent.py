"""
Marketing Agent - AI-Driven Autonomous Workflow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3.2] AI 자율 실행 에이전트
- 이벤트 분석 후 액션 제안
- Human-in-loop / Auto 모드
- 액션 실행 및 결과 추적
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class ApprovalMode(Enum):
    """승인 모드"""
    HUMAN_IN_LOOP = "human_in_loop"  # 모든 액션 수동 승인
    SEMI_AUTO = "semi_auto"          # 안전한 액션만 자동 실행
    FULL_AUTO = "full_auto"          # 모든 액션 자동 실행 (위험)


class ActionPriority(Enum):
    """액션 우선순위"""
    CRITICAL = 10   # 즉시 실행 필요
    HIGH = 8
    MEDIUM = 5
    LOW = 3
    OPTIONAL = 1


@dataclass
class RecommendedAction:
    """권장 액션"""
    action_name: str
    description: str
    priority: int
    auto_executable: bool
    parameters: Dict[str, Any]
    estimated_impact: str
    risk_level: str  # low, medium, high

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action_name,
            "description": self.description,
            "priority": self.priority,
            "auto_executable": self.auto_executable,
            "parameters": self.parameters,
            "estimated_impact": self.estimated_impact,
            "risk_level": self.risk_level
        }


@dataclass
class AgentDecision:
    """에이전트 결정"""
    trigger_event: str
    analysis: str
    recommended_actions: List[RecommendedAction]
    context_used: str
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class MarketingAgent:
    """
    마케팅 AI 에이전트

    이벤트를 분석하고, 컨텍스트를 수집하여, 최적의 액션을 제안/실행

    비용 제어 전략:
    1. 규칙 기반 우선 - 단순 이벤트는 AI 호출 없이 처리
    2. 이벤트 배치 - 유사 이벤트 모아서 한 번에 분석
    3. 쿨다운 - 동일 유형 이벤트는 시간 간격 적용
    4. 일일 한도 - AI 호출 일일 제한
    """

    # 비용 제어 설정
    DAILY_AI_CALL_LIMIT = 50  # 일일 AI 호출 제한
    COOLDOWN_MINUTES = 30     # 동일 이벤트 타입 쿨다운 (분)
    BATCH_WINDOW_SECONDS = 60 # 배치 수집 시간 (초)

    # AI가 필요한 복잡한 이벤트 타입 (나머지는 규칙 기반)
    AI_REQUIRED_EVENTS = {
        "competitor.weakness.detected",  # 경쟁사 약점 분석
        "rank.dropped",                   # 순위 급락 분석
        "lead.hot",                       # Hot Lead 분석
    }

    def __init__(self, approval_mode: ApprovalMode = ApprovalMode.HUMAN_IN_LOOP):
        self.approval_mode = approval_mode
        self.ai_client = None
        self.knowledge_base = None
        self.action_handlers: Dict[str, Callable] = {}

        # 비용 제어 상태
        self._daily_ai_calls = 0
        self._last_reset_date = datetime.now().date()
        self._last_event_times: Dict[str, datetime] = {}  # 이벤트 타입별 마지막 처리 시간
        self._event_batch: List[Dict] = []  # 배치 대기열

        self._init_ai()
        self._init_knowledge_base()
        self._register_default_handlers()
        logger.info(f"MarketingAgent initialized (mode: {approval_mode.value}, daily_limit: {self.DAILY_AI_CALL_LIMIT})")

    def _init_ai(self):
        """AI 클라이언트 초기화"""
        try:
            from google import genai
            from google.genai import types

            secrets_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'secrets.json'
            )

            api_key = None
            if os.path.exists(secrets_path):
                with open(secrets_path, 'r') as f:
                    secrets = json.load(f)
                    api_key = secrets.get('GEMINI_API_KEY') or secrets.get('GOOGLE_API_KEY')

            if not api_key:
                api_key = os.environ.get('GOOGLE_API_KEY')

            if api_key:
                self.ai_client = genai.Client(api_key=api_key)
                self.model_name = "gemini-3-flash-preview"  # CLAUDE.md 규칙
                self.generation_config = types.GenerateContentConfig(
                    temperature=0.3,
                    top_p=0.85
                )
                logger.info("AI client initialized successfully")
            else:
                logger.warning("No API key found, AI features disabled")

        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            self.ai_client = None

    def _init_knowledge_base(self):
        """지식 베이스 초기화"""
        try:
            from .knowledge_base import get_knowledge_base
            self.knowledge_base = get_knowledge_base()
        except Exception as e:
            logger.warning(f"Knowledge base not available: {e}")

    def _register_default_handlers(self):
        """기본 액션 핸들러 등록"""
        self.action_handlers = {
            "add_keyword": self._action_add_keyword,
            "send_alert": self._action_send_alert,
            "generate_blog_draft": self._action_generate_blog_draft,
            "update_priority": self._action_update_priority,
            "schedule_scan": self._action_schedule_scan,
            "log_insight": self._action_log_insight,
        }

    def register_action_handler(self, action_name: str, handler: Callable):
        """커스텀 액션 핸들러 등록"""
        self.action_handlers[action_name] = handler
        logger.debug(f"Registered action handler: {action_name}")

    # ============================================================
    # 핵심 분석 및 결정 메서드
    # ============================================================

    async def analyze_and_recommend(
        self,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> AgentDecision:
        """
        이벤트 분석 후 액션 권장

        비용 제어:
        1. 쿨다운 체크 - 동일 이벤트 타입 최근 처리 여부
        2. 일일 한도 체크 - AI 호출 제한
        3. 복잡도 판단 - 단순 이벤트는 규칙 기반 처리

        Args:
            event_type: 이벤트 타입
            event_data: 이벤트 데이터

        Returns:
            AgentDecision 객체
        """
        # 일일 카운터 리셋 체크
        self._check_daily_reset()

        # 1. 쿨다운 체크 - 최근에 같은 타입 이벤트 처리했으면 스킵
        if self._is_on_cooldown(event_type):
            logger.debug(f"Event {event_type} skipped (cooldown)")
            return self._create_skipped_decision(event_type, "cooldown")

        # 2. AI 사용 여부 결정
        use_ai = self._should_use_ai(event_type, event_data)

        if use_ai:
            # 일일 한도 체크
            if self._daily_ai_calls >= self.DAILY_AI_CALL_LIMIT:
                logger.warning(f"Daily AI call limit reached ({self.DAILY_AI_CALL_LIMIT})")
                use_ai = False

        # 3. 컨텍스트 수집 (AI 사용 시에만 전체 수집)
        if use_ai:
            context = await self._gather_context(event_type, event_data)
        else:
            context = f"[이벤트] {event_type}\n[데이터] {json.dumps(event_data, ensure_ascii=False)}"

        # 4. 분석 실행
        if use_ai and self.ai_client:
            analysis, actions = await self._ai_analyze(event_type, event_data, context)
            self._daily_ai_calls += 1
            logger.info(f"AI analysis used (daily count: {self._daily_ai_calls}/{self.DAILY_AI_CALL_LIMIT})")
        else:
            analysis, actions = self._rule_based_analyze(event_type, event_data)

        # 5. 쿨다운 기록
        self._last_event_times[event_type] = datetime.now()

        decision = AgentDecision(
            trigger_event=event_type,
            analysis=analysis,
            recommended_actions=actions,
            context_used=context[:500] + "..." if len(context) > 500 else context
        )

        # 6. DB에 기록
        self._log_decision(decision)

        return decision

    def _check_daily_reset(self):
        """일일 카운터 리셋 체크"""
        today = datetime.now().date()
        if today != self._last_reset_date:
            self._daily_ai_calls = 0
            self._last_reset_date = today
            logger.info("Daily AI call counter reset")

    def _is_on_cooldown(self, event_type: str) -> bool:
        """쿨다운 상태 체크"""
        last_time = self._last_event_times.get(event_type)
        if not last_time:
            return False

        elapsed = (datetime.now() - last_time).total_seconds() / 60
        return elapsed < self.COOLDOWN_MINUTES

    def _should_use_ai(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        AI 사용 여부 결정

        비용 절감을 위해 복잡한 이벤트에만 AI 사용
        """
        # 명시적으로 AI가 필요한 이벤트 타입
        if event_type in self.AI_REQUIRED_EVENTS:
            return True

        # 고등급 키워드 발견 - AI 분석 필요
        if "keyword" in event_type and event_data.get("grade") in ["S"]:
            return True

        # 대규모 순위 변동 - AI 분석 필요
        if "rank" in event_type:
            change = abs(event_data.get("change", 0))
            if change >= 10:
                return True

        # 그 외는 규칙 기반으로 충분
        return False

    def _create_skipped_decision(self, event_type: str, reason: str) -> AgentDecision:
        """스킵된 이벤트용 빈 결정 생성"""
        return AgentDecision(
            trigger_event=event_type,
            analysis=f"분석 스킵됨 (사유: {reason})",
            recommended_actions=[],
            context_used=""
        )

    def get_usage_stats(self) -> Dict[str, Any]:
        """API 사용 통계 반환"""
        return {
            "daily_ai_calls": self._daily_ai_calls,
            "daily_limit": self.DAILY_AI_CALL_LIMIT,
            "remaining": self.DAILY_AI_CALL_LIMIT - self._daily_ai_calls,
            "last_reset": self._last_reset_date.isoformat(),
            "cooldown_minutes": self.COOLDOWN_MINUTES,
            "active_cooldowns": [
                {"event": k, "remaining_minutes": round(self.COOLDOWN_MINUTES - (datetime.now() - v).total_seconds() / 60, 1)}
                for k, v in self._last_event_times.items()
                if (datetime.now() - v).total_seconds() / 60 < self.COOLDOWN_MINUTES
            ]
        }

    async def _gather_context(
        self,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> str:
        """관련 컨텍스트 수집"""
        context_parts = []

        # 이벤트 데이터
        context_parts.append(f"[이벤트] {event_type}")
        context_parts.append(f"[데이터] {json.dumps(event_data, ensure_ascii=False, indent=2)}")

        # 경쟁사 관련 이벤트면 지식 베이스 조회
        competitor_name = event_data.get("competitor_name") or event_data.get("competitor")
        if competitor_name and self.knowledge_base:
            kb_context = self.knowledge_base.get_context_for_analysis(competitor_name)
            context_parts.append(f"\n[기존 지식]\n{kb_context}")

        # 키워드 관련 이벤트면 순위 이력 조회
        keyword = event_data.get("keyword")
        if keyword:
            try:
                from db.database import DatabaseManager
                db = DatabaseManager()
                db.cursor.execute('''
                    SELECT rank, checked_at FROM rank_history
                    WHERE keyword = ? AND status = 'found'
                    ORDER BY checked_at DESC LIMIT 5
                ''', (keyword,))
                rank_history = db.cursor.fetchall()
                if rank_history:
                    context_parts.append(f"\n[순위 이력] {keyword}")
                    for rank, date in rank_history:
                        context_parts.append(f"  • {date}: {rank}위")
            except Exception as e:
                logger.debug(f"Failed to get rank history: {e}")

        return "\n".join(context_parts)

    async def _ai_analyze(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        context: str
    ) -> tuple:
        """AI 기반 분석"""
        prompt = f"""
당신은 마케팅 전문 AI 에이전트입니다. 다음 이벤트를 분석하고 최적의 마케팅 액션을 제안하세요.

{context}

다음 JSON 형식으로 응답하세요:
{{
    "analysis": "상황 분석 (2-3문장)",
    "recommended_actions": [
        {{
            "action": "액션명 (add_keyword, send_alert, generate_blog_draft, update_priority, schedule_scan, log_insight 중 하나)",
            "description": "액션 설명",
            "priority": 1-10 (높을수록 긴급),
            "auto_executable": true/false (자동 실행 가능 여부),
            "parameters": {{}},
            "estimated_impact": "예상 효과",
            "risk_level": "low/medium/high"
        }}
    ]
}}

제약사항:
- 최대 3개의 액션만 제안
- auto_executable은 위험도가 낮고 되돌릴 수 있는 액션에만 true
- 구체적이고 실행 가능한 액션만 제안
"""

        try:
            response = self.ai_client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config
            )

            result_text = response.text.strip()

            # JSON 추출
            json_match = result_text
            if "```json" in result_text:
                json_match = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                json_match = result_text.split("```")[1].split("```")[0]

            result = json.loads(json_match)

            analysis = result.get("analysis", "분석 결과 없음")
            actions = []

            for a in result.get("recommended_actions", []):
                actions.append(RecommendedAction(
                    action_name=a.get("action", "unknown"),
                    description=a.get("description", ""),
                    priority=a.get("priority", 5),
                    auto_executable=a.get("auto_executable", False),
                    parameters=a.get("parameters", {}),
                    estimated_impact=a.get("estimated_impact", ""),
                    risk_level=a.get("risk_level", "medium")
                ))

            return analysis, actions

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return self._rule_based_analyze(event_type, event_data)

    def _rule_based_analyze(
        self,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> tuple:
        """규칙 기반 분석 (AI 폴백)"""
        analysis = f"{event_type} 이벤트가 감지되었습니다."
        actions = []

        if "keyword" in event_type.lower():
            grade = event_data.get("grade", "")
            if grade in ["S", "A"]:
                actions.append(RecommendedAction(
                    action_name="add_keyword",
                    description="고등급 키워드를 추적 목록에 추가",
                    priority=8,
                    auto_executable=True,
                    parameters={"keyword": event_data.get("keyword")},
                    estimated_impact="순위 모니터링 시작",
                    risk_level="low"
                ))

        if "rank" in event_type.lower() and "drop" in event_type.lower():
            actions.append(RecommendedAction(
                action_name="send_alert",
                description="순위 급락 알림 전송",
                priority=9,
                auto_executable=True,
                parameters={"keyword": event_data.get("keyword"), "change": event_data.get("change")},
                estimated_impact="즉시 대응 가능",
                risk_level="low"
            ))

        if "competitor" in event_type.lower() and "weakness" in event_type.lower():
            actions.append(RecommendedAction(
                action_name="log_insight",
                description="경쟁사 약점 인사이트 기록",
                priority=7,
                auto_executable=True,
                parameters={"competitor": event_data.get("competitor_name"), "weaknesses": event_data.get("weaknesses")},
                estimated_impact="공략 포인트 확보",
                risk_level="low"
            ))

        if not actions:
            actions.append(RecommendedAction(
                action_name="log_insight",
                description="이벤트 기록 및 모니터링",
                priority=3,
                auto_executable=True,
                parameters={"event_type": event_type, "data": event_data},
                estimated_impact="데이터 축적",
                risk_level="low"
            ))

        return analysis, actions

    # ============================================================
    # 액션 실행
    # ============================================================

    async def execute_decision(
        self,
        decision: AgentDecision,
        approved_actions: List[str] = None
    ) -> Dict[str, Any]:
        """
        결정된 액션 실행

        Args:
            decision: AgentDecision 객체
            approved_actions: 승인된 액션 이름 목록 (None이면 모드에 따라 자동 결정)

        Returns:
            실행 결과
        """
        results = {
            "executed": [],
            "skipped": [],
            "failed": [],
            "pending_approval": []
        }

        for action in decision.recommended_actions:
            # 승인 체크
            should_execute = False

            if self.approval_mode == ApprovalMode.FULL_AUTO:
                should_execute = True
            elif self.approval_mode == ApprovalMode.SEMI_AUTO:
                should_execute = action.auto_executable and action.risk_level == "low"
            elif approved_actions and action.action_name in approved_actions:
                should_execute = True

            if not should_execute:
                if self.approval_mode == ApprovalMode.HUMAN_IN_LOOP:
                    results["pending_approval"].append(action.action_name)
                else:
                    results["skipped"].append(action.action_name)
                continue

            # 액션 실행
            try:
                handler = self.action_handlers.get(action.action_name)
                if handler:
                    await handler(action.parameters) if asyncio.iscoroutinefunction(handler) else handler(action.parameters)
                    results["executed"].append(action.action_name)
                    logger.info(f"Executed action: {action.action_name}")
                else:
                    results["skipped"].append(action.action_name)
                    logger.warning(f"No handler for action: {action.action_name}")

            except Exception as e:
                results["failed"].append({"action": action.action_name, "error": str(e)})
                logger.error(f"Action failed: {action.action_name} - {e}")

        # 결과 기록
        self._log_execution(decision, results)

        return results

    def _log_decision(self, decision: AgentDecision):
        """결정 로그 DB 저장"""
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            db.cursor.execute('''
                INSERT INTO agent_actions_log
                (trigger_event, analysis, recommended_actions, approval_status)
                VALUES (?, ?, ?, ?)
            ''', (
                decision.trigger_event,
                decision.analysis,
                json.dumps([a.to_dict() for a in decision.recommended_actions], ensure_ascii=False),
                "pending"
            ))
            db.conn.commit()

        except Exception as e:
            logger.error(f"Failed to log decision: {e}")

    def _log_execution(self, decision: AgentDecision, results: Dict[str, Any]):
        """실행 결과 로그 업데이트"""
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            status = "completed" if not results["failed"] else "partial"
            if not results["executed"]:
                status = "failed" if results["failed"] else "pending"

            db.cursor.execute('''
                UPDATE agent_actions_log
                SET executed_actions = ?,
                    execution_result = ?,
                    approval_status = ?,
                    executed_at = CURRENT_TIMESTAMP
                WHERE trigger_event = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (
                json.dumps(results["executed"], ensure_ascii=False),
                json.dumps(results, ensure_ascii=False),
                status,
                decision.trigger_event
            ))
            db.conn.commit()

        except Exception as e:
            logger.error(f"Failed to log execution: {e}")

    # ============================================================
    # 기본 액션 핸들러
    # ============================================================

    async def _action_add_keyword(self, params: Dict[str, Any]):
        """키워드 추가 액션"""
        keyword = params.get("keyword")
        if not keyword:
            return

        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'keywords.json'
            )

            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if keyword not in data.get("naver_place", []):
                data["naver_place"].append(keyword)

                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                logger.info(f"Added keyword to tracking: {keyword}")

        except Exception as e:
            logger.error(f"Failed to add keyword: {e}")

    async def _action_send_alert(self, params: Dict[str, Any]):
        """알림 전송 액션"""
        try:
            from alert_bot import AlertSystem, ActionableAlert, AlertPriority

            alert_system = AlertSystem()
            keyword = params.get("keyword", "Unknown")
            change = params.get("change", 0)

            alert = ActionableAlert(
                priority=AlertPriority.WARNING,
                title=f"[Agent] 순위 변동 감지: {keyword}",
                situation=f"'{keyword}' 키워드 순위가 {abs(change)}단계 변동되었습니다.",
                actions=["Battle Intelligence에서 상세 확인"],
                category="agent_alert"
            )
            alert_system.send_actionable_alert(alert)

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def _action_generate_blog_draft(self, params: Dict[str, Any]):
        """블로그 초안 생성 (Placeholder)"""
        logger.info(f"Blog draft generation requested: {params}")
        # 실제 구현은 별도 모듈에서

    async def _action_update_priority(self, params: Dict[str, Any]):
        """우선순위 업데이트 (Placeholder)"""
        logger.info(f"Priority update requested: {params}")

    async def _action_schedule_scan(self, params: Dict[str, Any]):
        """스캔 스케줄 (Placeholder)"""
        logger.info(f"Scan scheduled: {params}")

    async def _action_log_insight(self, params: Dict[str, Any]):
        """인사이트 기록"""
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            db.cursor.execute('''
                INSERT INTO insights (type, title, content, meta_json)
                VALUES (?, ?, ?, ?)
            ''', (
                "agent_insight",
                f"Agent Insight: {params.get('event_type', 'Event')}",
                json.dumps(params, ensure_ascii=False),
                "{}"
            ))
            db.conn.commit()

        except Exception as e:
            logger.error(f"Failed to log insight: {e}")


# 싱글톤 인스턴스
_marketing_agent = None


def get_marketing_agent(mode: ApprovalMode = ApprovalMode.SEMI_AUTO) -> MarketingAgent:
    """MarketingAgent 싱글톤 인스턴스 반환"""
    global _marketing_agent
    if _marketing_agent is None:
        _marketing_agent = MarketingAgent(approval_mode=mode)
    return _marketing_agent
