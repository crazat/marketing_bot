"""
AI Agent System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-1] Gemini 기반 마케팅 멀티 에이전트 시스템

에이전트:
- SEOAgent: 키워드 분석, 순위 전략
- ReviewAgent: 리뷰 감성 분석, 응답 전략
- ContentAgent: 블로그/SNS 콘텐츠 전략
- CompetitorAgent: 경쟁사 인텔리전스
- ReportAgent: 주간/월간 보고서 생성
- Orchestrator: 에이전트 조율 및 태스크 분배
"""

from services.ai_agents.base_agent import BaseAgent
from services.ai_agents.orchestrator import AgentOrchestrator

__all__ = ["BaseAgent", "AgentOrchestrator"]
