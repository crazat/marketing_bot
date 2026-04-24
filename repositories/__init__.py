"""Repository 레이어.

도메인별 DB 접근을 database.py에서 분리해 테스트·재사용 용이성 향상.

- ViralTargetRepository: viral_targets 테이블
- LeadRepository: mentions 테이블 (lead 관리)
- CompetitorRepository: competitor_reviews/weaknesses/rankings
- KeywordRepository: keyword_insights + rank_history

사용법:
    from repositories import ViralTargetRepository
    repo = ViralTargetRepository(db_path)
    rows = repo.list({"status": "pending"}, limit=50)
"""
from .viral_target_repo import ViralTargetRepository
from .lead_repo import LeadRepository
from .competitor_repo import CompetitorRepository
from .keyword_repo import KeywordRepository

__all__ = [
    "ViralTargetRepository",
    "LeadRepository",
    "CompetitorRepository",
    "KeywordRepository",
]
