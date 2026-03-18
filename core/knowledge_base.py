"""
Competitor Knowledge Base - Persistent AI Context
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3.1] 경쟁사 지식 프로파일
- 분석 결과 누적 저장
- AI 분석 시 컨텍스트로 활용
- 시간에 따른 인사이트 진화 추적
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    """지식 유형"""
    WEAKNESS = "weakness"          # 약점
    STRENGTH = "strength"          # 강점
    STRATEGY = "strategy"          # 전략
    TREND = "trend"                # 트렌드
    PRICING = "pricing"            # 가격 정책
    SERVICE = "service"            # 서비스 특징
    CUSTOMER_SENTIMENT = "sentiment"  # 고객 감성
    MARKETING = "marketing"        # 마케팅 활동


@dataclass
class KnowledgeEntry:
    """지식 항목"""
    id: int
    competitor_name: str
    knowledge_type: str
    content: str
    confidence: float
    source: str
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "competitor_name": self.competitor_name,
            "knowledge_type": self.knowledge_type,
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class CompetitorKnowledgeBase:
    """
    경쟁사 지식 베이스

    AI 분석 결과를 누적 저장하고, 새로운 분석 시 컨텍스트로 활용
    """

    def __init__(self):
        self.db = None
        self._init_db()
        logger.info("CompetitorKnowledgeBase initialized")

    def _init_db(self):
        """DB 연결"""
        try:
            from db.database import DatabaseManager
            self.db = DatabaseManager()
        except Exception as e:
            logger.error(f"Failed to initialize DB: {e}")

    # ============================================================
    # 지식 저장
    # ============================================================

    def add_knowledge(
        self,
        competitor_name: str,
        knowledge_type: str,
        content: str,
        confidence: float = 0.8,
        source: str = "auto"
    ) -> Optional[int]:
        """
        새 지식 항목 추가

        Args:
            competitor_name: 경쟁사 이름
            knowledge_type: 지식 유형
            content: 지식 내용
            confidence: 신뢰도 (0.0 ~ 1.0)
            source: 출처 (auto, manual, analysis 등)

        Returns:
            삽입된 행의 ID 또는 None
        """
        if not self.db:
            return None

        try:
            # 중복 체크 (동일한 내용이 이미 있는지)
            self.db.cursor.execute('''
                SELECT id FROM competitor_knowledge
                WHERE competitor_name = ? AND knowledge_type = ?
                  AND content = ?
            ''', (competitor_name, knowledge_type, content))

            existing = self.db.cursor.fetchone()
            if existing:
                # 기존 항목 업데이트 (신뢰도, 업데이트 시간)
                self.db.cursor.execute('''
                    UPDATE competitor_knowledge
                    SET confidence = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (confidence, existing[0]))
                self.db.conn.commit()
                return existing[0]

            # 새 항목 삽입
            self.db.cursor.execute('''
                INSERT INTO competitor_knowledge
                (competitor_name, knowledge_type, content, confidence, source)
                VALUES (?, ?, ?, ?, ?)
            ''', (competitor_name, knowledge_type, content, confidence, source))
            self.db.conn.commit()

            return self.db.cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            return None

    def add_knowledge_batch(
        self,
        competitor_name: str,
        knowledge_items: List[Dict[str, Any]],
        source: str = "analysis"
    ) -> int:
        """
        여러 지식 항목 일괄 추가

        Args:
            competitor_name: 경쟁사 이름
            knowledge_items: [{"type": "...", "content": "...", "confidence": 0.8}, ...]
            source: 출처

        Returns:
            추가된 항목 수
        """
        count = 0
        for item in knowledge_items:
            result = self.add_knowledge(
                competitor_name=competitor_name,
                knowledge_type=item.get("type", "general"),
                content=item.get("content", ""),
                confidence=item.get("confidence", 0.8),
                source=source
            )
            if result:
                count += 1

        logger.info(f"Added {count} knowledge items for {competitor_name}")
        return count

    # ============================================================
    # 지식 조회
    # ============================================================

    def get_knowledge(
        self,
        competitor_name: str,
        knowledge_type: Optional[str] = None,
        limit: int = 20,
        min_confidence: float = 0.5
    ) -> List[KnowledgeEntry]:
        """
        경쟁사 지식 조회

        Args:
            competitor_name: 경쟁사 이름
            knowledge_type: 특정 유형만 조회 (None이면 전체)
            limit: 최대 조회 수
            min_confidence: 최소 신뢰도

        Returns:
            KnowledgeEntry 목록
        """
        if not self.db:
            return []

        try:
            if knowledge_type:
                self.db.cursor.execute('''
                    SELECT id, competitor_name, knowledge_type, content,
                           confidence, source, created_at, updated_at
                    FROM competitor_knowledge
                    WHERE competitor_name = ?
                      AND knowledge_type = ?
                      AND confidence >= ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                ''', (competitor_name, knowledge_type, min_confidence, limit))
            else:
                self.db.cursor.execute('''
                    SELECT id, competitor_name, knowledge_type, content,
                           confidence, source, created_at, updated_at
                    FROM competitor_knowledge
                    WHERE competitor_name = ?
                      AND confidence >= ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                ''', (competitor_name, min_confidence, limit))

            rows = self.db.cursor.fetchall()

            entries = []
            for row in rows:
                try:
                    created = datetime.fromisoformat(row[6]) if row[6] else None
                    updated = datetime.fromisoformat(row[7]) if row[7] else None
                except Exception:
                    created = updated = None

                entries.append(KnowledgeEntry(
                    id=row[0],
                    competitor_name=row[1],
                    knowledge_type=row[2],
                    content=row[3],
                    confidence=row[4],
                    source=row[5],
                    created_at=created,
                    updated_at=updated
                ))

            return entries

        except Exception as e:
            logger.error(f"Failed to get knowledge: {e}")
            return []

    def get_context_for_analysis(self, competitor_name: str, max_tokens: int = 2000) -> str:
        """
        AI 분석용 컨텍스트 문자열 생성

        Args:
            competitor_name: 경쟁사 이름
            max_tokens: 최대 토큰 수 (대략적인 문자 수로 계산)

        Returns:
            컨텍스트 문자열
        """
        knowledge = self.get_knowledge(competitor_name, limit=30)

        if not knowledge:
            return f"'{competitor_name}'에 대한 기존 분석 데이터가 없습니다."

        # 유형별 그룹화
        by_type = {}
        for k in knowledge:
            if k.knowledge_type not in by_type:
                by_type[k.knowledge_type] = []
            by_type[k.knowledge_type].append(k)

        # 컨텍스트 빌드
        lines = [
            f"=== {competitor_name} 기존 분석 컨텍스트 ===",
            f"(최근 업데이트: {knowledge[0].updated_at.strftime('%Y-%m-%d') if knowledge[0].updated_at else 'N/A'})",
            ""
        ]

        type_labels = {
            "weakness": "약점",
            "strength": "강점",
            "strategy": "전략",
            "trend": "트렌드",
            "pricing": "가격",
            "service": "서비스",
            "sentiment": "고객 감성",
            "marketing": "마케팅"
        }

        for k_type, entries in by_type.items():
            label = type_labels.get(k_type, k_type)
            lines.append(f"[{label}]")
            for entry in entries[:5]:  # 유형당 최대 5개
                conf_indicator = "●" * int(entry.confidence * 5)
                lines.append(f"  • {entry.content} ({conf_indicator})")
            lines.append("")

        context = "\n".join(lines)

        # 최대 길이 제한
        if len(context) > max_tokens * 4:  # 대략 4자 = 1토큰
            context = context[:max_tokens * 4] + "\n... (추가 컨텍스트 생략)"

        return context

    # ============================================================
    # 지식 업데이트 및 분석 결과 반영
    # ============================================================

    def update_from_analysis(
        self,
        competitor_name: str,
        analysis_result: Dict[str, Any]
    ) -> int:
        """
        분석 결과를 지식 베이스에 반영

        Args:
            competitor_name: 경쟁사 이름
            analysis_result: AI 분석 결과 딕셔너리
                {
                    "weaknesses": ["약점1", "약점2"],
                    "strengths": ["강점1"],
                    "strategies": ["전략1"],
                    "sentiment": "positive/negative/neutral",
                    "sentiment_details": "감성 상세 분석",
                    ...
                }

        Returns:
            추가/업데이트된 항목 수
        """
        count = 0

        # 약점 추가
        for weakness in analysis_result.get("weaknesses", []):
            if self.add_knowledge(competitor_name, "weakness", weakness, 0.85, "analysis"):
                count += 1

        # 강점 추가
        for strength in analysis_result.get("strengths", []):
            if self.add_knowledge(competitor_name, "strength", strength, 0.85, "analysis"):
                count += 1

        # 전략 추가
        for strategy in analysis_result.get("strategies", []):
            if self.add_knowledge(competitor_name, "strategy", strategy, 0.75, "analysis"):
                count += 1

        # 감성 분석 추가
        sentiment_details = analysis_result.get("sentiment_details")
        if sentiment_details:
            self.add_knowledge(competitor_name, "sentiment", sentiment_details, 0.8, "analysis")
            count += 1

        # 가격 정보 추가
        pricing_info = analysis_result.get("pricing")
        if pricing_info:
            self.add_knowledge(competitor_name, "pricing", pricing_info, 0.7, "analysis")
            count += 1

        logger.info(f"Updated knowledge base: {competitor_name} ({count} items)")
        return count

    # ============================================================
    # 지식 통계 및 관리
    # ============================================================

    def get_knowledge_stats(self, competitor_name: str = None) -> Dict[str, Any]:
        """지식 통계 조회"""
        if not self.db:
            return {}

        try:
            if competitor_name:
                self.db.cursor.execute('''
                    SELECT knowledge_type, COUNT(*), AVG(confidence)
                    FROM competitor_knowledge
                    WHERE competitor_name = ?
                    GROUP BY knowledge_type
                ''', (competitor_name,))
            else:
                self.db.cursor.execute('''
                    SELECT competitor_name, COUNT(*)
                    FROM competitor_knowledge
                    GROUP BY competitor_name
                ''')

            rows = self.db.cursor.fetchall()

            if competitor_name:
                return {
                    "competitor": competitor_name,
                    "by_type": {row[0]: {"count": row[1], "avg_confidence": round(row[2], 2)} for row in rows},
                    "total": sum(row[1] for row in rows)
                }
            else:
                return {
                    "by_competitor": {row[0]: row[1] for row in rows},
                    "total": sum(row[1] for row in rows)
                }

        except Exception as e:
            logger.error(f"Failed to get knowledge stats: {e}")
            return {}

    def cleanup_old_knowledge(self, days: int = 90, min_confidence: float = 0.3) -> int:
        """
        오래되고 신뢰도 낮은 지식 정리

        Args:
            days: 이 기간 이전에 업데이트된 항목 대상
            min_confidence: 이 신뢰도 이하 항목 삭제

        Returns:
            삭제된 항목 수
        """
        if not self.db:
            return 0

        try:
            self.db.cursor.execute('''
                DELETE FROM competitor_knowledge
                WHERE updated_at < date('now', ?)
                  AND confidence < ?
            ''', (f'-{days} days', min_confidence))

            deleted = self.db.cursor.rowcount
            self.db.conn.commit()

            logger.info(f"Cleaned up {deleted} old knowledge items")
            return deleted

        except Exception as e:
            logger.error(f"Failed to cleanup knowledge: {e}")
            return 0

    def get_all_competitors(self) -> List[str]:
        """지식이 저장된 모든 경쟁사 목록"""
        if not self.db:
            return []

        try:
            self.db.cursor.execute('''
                SELECT DISTINCT competitor_name FROM competitor_knowledge
                ORDER BY competitor_name
            ''')
            return [row[0] for row in self.db.cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get competitors: {e}")
            return []


# 싱글톤 인스턴스
_knowledge_base = None


def get_knowledge_base() -> CompetitorKnowledgeBase:
    """CompetitorKnowledgeBase 싱글톤 인스턴스 반환"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = CompetitorKnowledgeBase()
    return _knowledge_base
