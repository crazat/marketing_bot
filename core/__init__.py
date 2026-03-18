# Core module - Phase 2 & 3 Intelligence Layer
"""
Marketing Bot Core Module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 2 구현 완료:
- 2.1 Event-Driven Architecture (이벤트 버스)
- 2.2 Workflow Chaining (자동 워크플로우)
- 2.3 Adaptive Scheduling (적응형 스케줄링)
- 2.4 Time-Series Analytics (시계열 분석)
- 2.5 Cross-Module Insights (모듈 간 인사이트)

Phase 3 구현 완료:
- 3.1 Persistent AI Context (경쟁사 지식 프로파일)
- 3.2 Agentic Workflow (AI 자율 실행)
- 3.3 Command Palette (자연어 인터페이스) [Frontend]
"""

from .event_bus import EventBus, EventType, Event, get_event_bus, publish_event
from .workflow_engine import (
    WorkflowEngine, WorkflowStep, WorkflowStatus,
    get_workflow_engine, setup_default_workflows
)
from .adaptive_scheduler import (
    AdaptiveScheduler, ScheduleHealth, get_adaptive_scheduler
)
from .analytics import (
    TimeSeriesAnalyzer, TrendAnalysis, get_time_series_analyzer
)
from .insights import (
    CrossModuleInsightsEngine, MarketingInsight, get_insights_engine
)
from .knowledge_base import (
    CompetitorKnowledgeBase, KnowledgeType, get_knowledge_base
)
from .marketing_agent import (
    MarketingAgent, ApprovalMode, RecommendedAction, get_marketing_agent
)

__all__ = [
    # Event Bus (Phase 2.1)
    'EventBus', 'EventType', 'Event', 'get_event_bus', 'publish_event',
    # Workflow Engine (Phase 2.2)
    'WorkflowEngine', 'WorkflowStep', 'WorkflowStatus',
    'get_workflow_engine', 'setup_default_workflows',
    # Adaptive Scheduler (Phase 2.3)
    'AdaptiveScheduler', 'ScheduleHealth', 'get_adaptive_scheduler',
    # Analytics (Phase 2.4)
    'TimeSeriesAnalyzer', 'TrendAnalysis', 'get_time_series_analyzer',
    # Insights (Phase 2.5)
    'CrossModuleInsightsEngine', 'MarketingInsight', 'get_insights_engine',
    # Knowledge Base (Phase 3.1)
    'CompetitorKnowledgeBase', 'KnowledgeType', 'get_knowledge_base',
    # Marketing Agent (Phase 3.2)
    'MarketingAgent', 'ApprovalMode', 'RecommendedAction', 'get_marketing_agent'
]
