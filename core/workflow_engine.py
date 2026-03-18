"""
Workflow Engine - Event-Driven Workflow Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2.2] 이벤트 기반 자동 워크플로우 체이닝
- 이벤트 발생 시 자동 후속 작업 실행
- 조건부 워크플로우 분기
- 워크플로우 실행 이력 관리
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum

from .event_bus import EventBus, EventType, Event, get_event_bus, publish_event

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """워크플로우 실행 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """워크플로우 단계 정의"""
    name: str
    action: Callable
    condition: Optional[Callable] = None  # 실행 조건 (True면 실행)
    on_success: Optional[str] = None  # 성공 시 다음 스텝
    on_failure: Optional[str] = None  # 실패 시 다음 스텝
    timeout_seconds: int = 300


@dataclass
class WorkflowExecution:
    """워크플로우 실행 기록"""
    workflow_name: str
    trigger_event: str
    started_at: datetime
    steps_completed: List[str]
    status: WorkflowStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    finished_at: Optional[datetime] = None


class WorkflowEngine:
    """
    이벤트 기반 워크플로우 엔진

    사용 예:
    ```python
    engine = WorkflowEngine()

    # 워크플로우 정의
    engine.register_workflow(
        name="keyword_to_rank_check",
        trigger=EventType.KEYWORD_DISCOVERED,
        steps=[
            WorkflowStep("check_rank", check_keyword_rank),
            WorkflowStep("notify_if_top10", send_notification,
                         condition=lambda ctx: ctx.get('rank', 100) <= 10)
        ]
    )

    # 엔진 시작
    engine.start()
    ```
    """

    def __init__(self):
        self.event_bus = get_event_bus()
        self.workflows: Dict[str, Dict] = {}
        self.executions: List[WorkflowExecution] = []
        self.max_executions = 500
        self._running = False
        logger.info("WorkflowEngine initialized")

    def register_workflow(
        self,
        name: str,
        trigger: EventType,
        steps: List[WorkflowStep],
        condition: Optional[Callable] = None,
        enabled: bool = True
    ):
        """
        워크플로우 등록

        Args:
            name: 워크플로우 이름
            trigger: 트리거 이벤트 타입
            steps: 실행할 스텝 목록
            condition: 전체 워크플로우 실행 조건
            enabled: 활성화 여부
        """
        self.workflows[name] = {
            "name": name,
            "trigger": trigger,
            "steps": steps,
            "condition": condition,
            "enabled": enabled
        }

        # 이벤트 구독
        self.event_bus.subscribe_async(trigger, self._create_workflow_handler(name))
        logger.info(f"Workflow registered: {name} (trigger: {trigger.value})")

    def _create_workflow_handler(self, workflow_name: str):
        """이벤트 핸들러 생성"""
        async def handler(event: Event):
            await self._execute_workflow(workflow_name, event)
        return handler

    async def _execute_workflow(self, workflow_name: str, event: Event):
        """워크플로우 실행"""
        workflow = self.workflows.get(workflow_name)
        if not workflow or not workflow.get("enabled"):
            return

        # 실행 조건 체크
        if workflow.get("condition"):
            try:
                if not workflow["condition"](event.data):
                    logger.debug(f"Workflow {workflow_name} skipped (condition not met)")
                    return
            except Exception as e:
                logger.error(f"Workflow condition check failed: {e}")
                return

        execution = WorkflowExecution(
            workflow_name=workflow_name,
            trigger_event=event.event_type.value,
            started_at=datetime.now(),
            steps_completed=[],
            status=WorkflowStatus.RUNNING
        )

        logger.info(f"🔄 Workflow started: {workflow_name}")

        # 컨텍스트 초기화 (이벤트 데이터로 시작)
        context = dict(event.data)
        context["_event"] = event
        context["_workflow"] = workflow_name

        try:
            for step in workflow["steps"]:
                # 스텝 조건 체크
                if step.condition:
                    try:
                        if not step.condition(context):
                            logger.debug(f"Step {step.name} skipped (condition not met)")
                            continue
                    except Exception as e:
                        logger.error(f"Step condition check failed: {e}")
                        continue

                # 스텝 실행
                logger.debug(f"Executing step: {step.name}")
                try:
                    if asyncio.iscoroutinefunction(step.action):
                        result = await asyncio.wait_for(
                            step.action(context),
                            timeout=step.timeout_seconds
                        )
                    else:
                        result = step.action(context)

                    # 결과를 컨텍스트에 병합
                    if isinstance(result, dict):
                        context.update(result)

                    execution.steps_completed.append(step.name)

                except asyncio.TimeoutError:
                    logger.error(f"Step {step.name} timed out")
                    execution.status = WorkflowStatus.FAILED
                    execution.error = f"Step {step.name} timeout"
                    break

                except Exception as e:
                    logger.error(f"Step {step.name} failed: {e}")
                    execution.status = WorkflowStatus.FAILED
                    execution.error = str(e)
                    break

            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.COMPLETED
                execution.result = {k: v for k, v in context.items() if not k.startswith("_")}

        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)
            logger.error(f"Workflow {workflow_name} failed: {e}")

        execution.finished_at = datetime.now()
        self._record_execution(execution)

        # 워크플로우 완료 이벤트 발행
        try:
            publish_event(
                EventType.SCAN_COMPLETED,  # 임시로 SCAN_COMPLETED 사용
                {
                    "workflow_name": workflow_name,
                    "status": execution.status.value,
                    "steps_completed": execution.steps_completed,
                    "duration_seconds": (execution.finished_at - execution.started_at).total_seconds()
                },
                source="workflow_engine"
            )
        except Exception as e:
            logger.warning(f"Failed to publish workflow completion event: {e}")

        logger.info(f"✅ Workflow completed: {workflow_name} (status: {execution.status.value})")

    def _record_execution(self, execution: WorkflowExecution):
        """실행 기록 저장"""
        self.executions.append(execution)

        # 최대 기록 수 제한
        if len(self.executions) > self.max_executions:
            self.executions = self.executions[-self.max_executions:]

        # DB에 저장
        self._save_to_db(execution)

    def _save_to_db(self, execution: WorkflowExecution):
        """실행 기록을 DB에 저장"""
        try:
            import json
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from db.database import DatabaseManager
            db = DatabaseManager()

            db.cursor.execute('''
                INSERT INTO schedule_history
                (job_name, executed_at, status, duration_seconds, result)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                f"workflow:{execution.workflow_name}",
                execution.started_at.isoformat(),
                execution.status.value,
                (execution.finished_at - execution.started_at).total_seconds() if execution.finished_at else 0,
                json.dumps({
                    "steps": execution.steps_completed,
                    "error": execution.error,
                    "result": execution.result
                }, ensure_ascii=False)
            ))
            db.conn.commit()
        except Exception as e:
            logger.debug(f"Failed to save workflow execution to DB: {e}")

    def get_workflow_stats(self) -> Dict[str, Any]:
        """워크플로우 통계 조회"""
        stats = {
            "total_executions": len(self.executions),
            "by_status": {},
            "by_workflow": {},
            "recent": []
        }

        for exec in self.executions:
            # 상태별 집계
            status = exec.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # 워크플로우별 집계
            name = exec.workflow_name
            if name not in stats["by_workflow"]:
                stats["by_workflow"][name] = {"total": 0, "completed": 0, "failed": 0}
            stats["by_workflow"][name]["total"] += 1
            if exec.status == WorkflowStatus.COMPLETED:
                stats["by_workflow"][name]["completed"] += 1
            elif exec.status == WorkflowStatus.FAILED:
                stats["by_workflow"][name]["failed"] += 1

        # 최근 10개
        stats["recent"] = [
            {
                "workflow": e.workflow_name,
                "status": e.status.value,
                "started": e.started_at.isoformat(),
                "steps": len(e.steps_completed)
            }
            for e in self.executions[-10:]
        ]

        return stats

    def enable_workflow(self, name: str):
        """워크플로우 활성화"""
        if name in self.workflows:
            self.workflows[name]["enabled"] = True
            logger.info(f"Workflow enabled: {name}")

    def disable_workflow(self, name: str):
        """워크플로우 비활성화"""
        if name in self.workflows:
            self.workflows[name]["enabled"] = False
            logger.info(f"Workflow disabled: {name}")


# ============================================================
# 기본 워크플로우 액션 함수들
# ============================================================

def action_check_keyword_rank(context: Dict[str, Any]) -> Dict[str, Any]:
    """키워드 순위 체크 액션"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from db.database import DatabaseManager

        db = DatabaseManager()
        keyword = context.get("keyword") or context.get("term", "")

        if not keyword:
            return {"rank": None, "rank_found": False}

        # 최근 순위 조회
        db.cursor.execute('''
            SELECT rank, status FROM rank_history
            WHERE keyword = ? AND status = 'found'
            ORDER BY checked_at DESC LIMIT 1
        ''', (keyword,))
        row = db.cursor.fetchone()

        if row:
            return {"rank": row[0], "rank_status": row[1], "rank_found": True}
        return {"rank": None, "rank_found": False}

    except Exception as e:
        logger.error(f"action_check_keyword_rank failed: {e}")
        return {"rank": None, "rank_found": False, "error": str(e)}


def action_notify_high_grade_keyword(context: Dict[str, Any]) -> Dict[str, Any]:
    """고등급 키워드 발견 알림"""
    try:
        grade = context.get("grade", "")
        keyword = context.get("keyword") or context.get("term", "")

        if grade in ["S", "A"]:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from alert_bot import AlertSystem, ActionableAlert, AlertPriority

            alert_system = AlertSystem()
            alert = ActionableAlert(
                priority=AlertPriority.INFO if grade == "A" else AlertPriority.WARNING,
                title=f"고가치 키워드 발견: {keyword}",
                situation=f"등급 {grade} 키워드가 발견되었습니다.",
                analysis=f"검색량: {context.get('search_volume', 'N/A')}, 경쟁도: {context.get('competition', 'N/A')}",
                actions=[
                    "키워드를 추적 목록에 추가",
                    "관련 블로그 콘텐츠 기획"
                ],
                deep_link="http://localhost:3000/pathfinder",
                category="keyword_discovery"
            )
            alert_system.send_actionable_alert(alert)
            return {"notification_sent": True}

        return {"notification_sent": False}

    except Exception as e:
        logger.error(f"action_notify_high_grade_keyword failed: {e}")
        return {"notification_sent": False, "error": str(e)}


def action_notify_rank_drop(context: Dict[str, Any]) -> Dict[str, Any]:
    """순위 급락 알림"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from alert_bot import AlertSystem, ActionableAlert, AlertPriority

        keyword = context.get("keyword", "Unknown")
        current_rank = context.get("current_rank", 0)
        previous_rank = context.get("previous_rank", 0)
        change = context.get("change", 0)

        alert_system = AlertSystem()
        alert = ActionableAlert(
            priority=AlertPriority.CRITICAL,
            title=f"순위 급락: {keyword}",
            situation=f"'{keyword}' 키워드가 {previous_rank}위 → {current_rank}위로 {abs(change)}계단 하락했습니다.",
            analysis="경쟁사 활동 증가 또는 알고리즘 변동이 원인일 수 있습니다.",
            actions=[
                "경쟁사 활동 확인",
                "콘텐츠 개선 검토",
                "대체 키워드 발굴"
            ],
            deep_link="http://localhost:3000/battle",
            category="rank_drop"
        )
        alert_system.send_actionable_alert(alert)
        return {"notification_sent": True}

    except Exception as e:
        logger.error(f"action_notify_rank_drop failed: {e}")
        return {"notification_sent": False, "error": str(e)}


def action_log_competitor_weakness(context: Dict[str, Any]) -> Dict[str, Any]:
    """경쟁사 약점을 DB에 기록"""
    try:
        import sys
        import os
        import json
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from db.database import DatabaseManager

        db = DatabaseManager()
        competitor_name = context.get("competitor_name", "Unknown")
        weaknesses = context.get("weaknesses", [])

        for weakness in weaknesses:
            db.cursor.execute('''
                INSERT OR IGNORE INTO competitor_weaknesses
                (competitor_name, weakness_type, description, source, discovered_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                competitor_name,
                "auto_detected",
                weakness,
                "workflow_engine",
                datetime.now().isoformat()
            ))

        db.conn.commit()
        return {"weaknesses_logged": len(weaknesses)}

    except Exception as e:
        logger.error(f"action_log_competitor_weakness failed: {e}")
        return {"weaknesses_logged": 0, "error": str(e)}


# ============================================================
# 기본 워크플로우 설정
# ============================================================

def setup_default_workflows(engine: WorkflowEngine):
    """기본 워크플로우 등록"""

    # 1. 고등급 키워드 발견 → 알림
    engine.register_workflow(
        name="keyword_discovery_alert",
        trigger=EventType.KEYWORD_DISCOVERED,
        steps=[
            WorkflowStep(
                name="notify",
                action=action_notify_high_grade_keyword,
                condition=lambda ctx: ctx.get("grade") in ["S", "A"]
            )
        ],
        condition=lambda data: data.get("count", 0) > 0
    )

    # 2. 순위 급락 → 알림
    engine.register_workflow(
        name="rank_drop_alert",
        trigger=EventType.RANK_DROPPED,
        steps=[
            WorkflowStep(
                name="notify",
                action=action_notify_rank_drop
            )
        ]
    )

    # 3. 경쟁사 약점 발견 → DB 기록
    engine.register_workflow(
        name="competitor_weakness_log",
        trigger=EventType.COMPETITOR_WEAKNESS_DETECTED,
        steps=[
            WorkflowStep(
                name="log_to_db",
                action=action_log_competitor_weakness
            )
        ]
    )

    logger.info(f"Registered {len(engine.workflows)} default workflows")


# 싱글톤 인스턴스
_workflow_engine = None

def get_workflow_engine() -> WorkflowEngine:
    """WorkflowEngine 싱글톤 인스턴스 반환"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
        setup_default_workflows(_workflow_engine)
    return _workflow_engine
