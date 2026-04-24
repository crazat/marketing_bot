"""
Base Agent - 모든 AI 에이전트의 기본 클래스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

각 에이전트는 역할(role), 목표(goal), 도구(tools)를 가지며
AI API를 통해 추론하고 DB에서 데이터를 조회합니다.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from abc import ABC, abstractmethod

from services.ai_client import ai_generate, ai_generate_json

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """AI 에이전트 기본 클래스"""

    def __init__(self, name: str, role: str, goal: str, db_path: str = None):
        self.name = name
        self.role = role
        self.goal = goal
        self.db_path = db_path

    async def think(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """AI에게 추론 요청"""
        system_prompt = f"당신은 {self.role}입니다.\n목표: {self.goal}"

        try:
            return ai_generate(prompt, temperature=temperature, max_tokens=max_tokens, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"[{self.name}] 추론 실패: {e}")
            return f"[{self.name}] 추론 오류: {str(e)}"

    async def think_json(self, prompt: str, temperature: float = 0.3) -> Optional[Dict]:
        """AI에게 JSON 형식 응답 요청"""
        system_prompt = f"당신은 {self.role}입니다.\n목표: {self.goal}"

        try:
            return ai_generate_json(prompt, temperature=temperature, max_tokens=1500, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"[{self.name}] JSON 추론 실패: {e}")
            return None

    def query_db(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """DB 조회 헬퍼"""
        if not self.db_path:
            return []
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[{self.name}] DB 조회 실패: {e}")
            return []
        finally:
            if conn:
                conn.close()

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """에이전트 태스크 실행 (서브클래스에서 구현)"""
        pass
