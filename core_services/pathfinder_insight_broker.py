"""Pathfinder insight broker.

Turns keyword_insights rows into user-facing briefs and agent handoff packets.
The broker is intentionally deterministic so it can be used before or inside
Codex/LLM prompts without making another model call.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


AGENT_ALIASES = {
    "blog": "blog_agent",
    "blog_agent": "blog_agent",
    "content": "blog_agent",
    "content_agent": "blog_agent",
    "shorts": "shorts_studio_agent",
    "shorts_studio": "shorts_studio_agent",
    "shorts_studio_agent": "shorts_studio_agent",
    "reels": "shorts_studio_agent",
    "viral": "viral_hunter_agent",
    "viral_hunter": "viral_hunter_agent",
    "viral_hunter_agent": "viral_hunter_agent",
    "ads": "ad_agent",
    "ad": "ad_agent",
    "ad_agent": "ad_agent",
}


def _json_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return [value] if value else []
    return []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class PathfinderInsightBroker:
    """Builds cross-agent insight contracts from Pathfinder output."""

    VERSION = "pathfinder.insight.v1"

    TEXT_DEFAULTS: Dict[str, str] = {
        "keyword": "",
        "competition": "",
        "grade": "C",
        "category": "기타",
        "source": "",
        "trend_status": "unknown",
        "search_intent": "unknown",
        "content_cluster_key": "",
        "rank_status": "unknown",
        "availability_intent_type": "none",
        "payment_coverage_type": "none",
        "access_convenience_type": "none",
        "recommended_content_type": "",
        "preferred_search_surface": "",
        "brand_intent_type": "generic",
        "review_intent_type": "none",
        "quality_flags_json": "[]",
        "source_signals_json": "[]",
        "created_at": "",
        "updated_at": "",
    }

    NUMERIC_DEFAULTS: Dict[str, float] = {
        "search_volume": 0,
        "difficulty": 50,
        "opportunity": 50,
        "priority_v3": 0,
        "opp_score": 0,
        "document_count": 0,
        "kei": 0,
        "business_core": 0,
        "longtail_score": 0,
        "business_value_score": 0,
        "high_value_longtail": 0,
        "mobile_share": 0,
        "rank_gap_signal": 0,
        "community_signal": 0,
        "conversion_signal": 0,
        "profile_action_signal": 0,
        "availability_intent_score": 0,
        "payment_coverage_score": 0,
        "access_convenience_score": 0,
        "medical_ad_risk_score": 0,
        "content_actionability_score": 0,
        "local_service_fit_score": 0,
        "local_surface_score": 0,
        "brand_signal_score": 0,
        "competitor_brand_risk_score": 0,
        "review_surface_score": 0,
        "reputation_risk_score": 0,
        "verification_score": 0,
        "novelty_score": 0,
        "last_scan_run_id": 0,
    }

    PLACE_RANK_RESEARCH_BASIS: List[Dict[str, str]] = [
        {
            "lever": "keyword_relevance",
            "finding": "플레이스 검색은 검색어와 업체 정보의 유사도, 업종, 대표키워드, 주소 정보를 함께 본다.",
            "system_use": "순위가 없거나 낮은 키워드는 업종, 대표키워드, 메뉴/서비스명, 상세설명의 정합성 점검 액션으로 전환한다.",
        },
        {
            "lever": "information_completeness",
            "finding": "정확하고 풍부한 스마트플레이스 정보는 검색어 매칭과 방문 경험, 리뷰 신뢰의 기반이 된다.",
            "system_use": "영업시간, 휴무, 사진, 메뉴/서비스, 찾아오는 길, 주차/시설, 예약/주문, 홈페이지/SNS 보완을 체크리스트화한다.",
        },
        {
            "lever": "authentic_visit_feedback",
            "finding": "실제 방문 경험과 일치하는 리뷰 흐름은 신뢰 신호가 되지만 허위/조작 리뷰는 업체 단위 페널티 대상이다.",
            "system_use": "실방문 고객에게 자율 리뷰를 안내하고 답글/FAQ로 전환하되 별점, 문구, 보상을 통제하지 않도록 차단한다.",
        },
        {
            "lever": "freshness_and_trend",
            "finding": "순위는 이용도, 정보의 질, 추이도 등 여러 요소로 수시 변동된다.",
            "system_use": "rank_history의 하락, 미노출, 경쟁사 선점 신호를 주간 점검과 복구 액션으로 연결한다.",
        },
        {
            "lever": "local_content_alignment",
            "finding": "업체 정보와 주변 콘텐츠가 같은 지역·서비스 의도를 자연스럽게 설명할 때 검색어 적합성이 좋아진다.",
            "system_use": "블로그, 숏폼, FAQ, 랜딩 문구가 대표키워드와 실제 제공 서비스에 맞는지 검증한다.",
        },
    ]

    PLACE_RANK_PROHIBITED_TACTICS: List[str] = [
        "허위 클릭, 저장, 공유, 트래픽 유발 프로그램",
        "허위 예약 생성 후 취소 또는 예약 판매 건수 조작",
        "가짜 영수증, 타인 영수증, AI/편집 영수증을 이용한 허위 리뷰",
        "금전/혜택을 조건으로 실제 경험 없는 리뷰를 작성하게 하는 방식",
        "특정 별점, 긍정 문구, 리뷰 수정/삭제를 강요하거나 현장에서 통제하는 방식",
        "업체와 무관한 홍보성/주관적 대표키워드 삽입과 키워드 스터핑",
        "업체명·주소·상세설명에 상업 키워드나 지역명을 반복 삽입하는 방식",
        "순위 조작 목적의 백링크 구매, 리다이렉트, 도메인 포워딩, 스팸성 SEO",
        "경쟁사 비방, 신고 남용, 평판 공격",
    ]

    PLACE_RANK_SOURCE_REFS: List[Dict[str, str]] = [
        {
            "title": "네이버 스마트플레이스: 플레이스 업체 검색 순위를 높이는 방법",
            "url": "https://help.naver.com/service/30026/contents/23473",
            "use": "순위 개선을 정보 충실성, 검색어 적합성, 실제 이용 경험 관리로 제한",
        },
        {
            "title": "네이버 스마트플레이스: 지도 검색 결과 노출 기준",
            "url": "https://help.naver.com/service/30026/contents/20402?lang=ko",
            "use": "지도/플레이스 노출 상태를 no_results, not_in_results, found로 구분",
        },
        {
            "title": "네이버 스마트플레이스: 검색 결과 어뷰징 판정 기준",
            "url": "https://help.naver.com/service/30026/contents/23474?lang=ko",
            "use": "클릭, 저장, 예약, 리뷰 조작을 금지 수단으로 차단",
        },
        {
            "title": "네이버 스마트플레이스: 방문자리뷰 업체 단위 페널티",
            "url": "https://help.naver.com/service/30026/contents/25091?lang=ko",
            "use": "실방문 리뷰 루프를 별점/문구/보상 통제 없이 운영",
        },
        {
            "title": "네이버 서치어드바이저: 사이트 진단",
            "url": "https://searchadvisor.naver.com/diagnose",
            "use": "플레이스와 연결되는 홈페이지/랜딩의 제목, 설명, 로봇 차단 상태 점검",
        },
        {
            "title": "네이버 서치어드바이저: 웹 검색 미노출",
            "url": "https://searchadvisor.naver.com/guide/faq-serpmissing",
            "use": "콘텐츠 미노출 시 색인, 수집, robots, 사이트 기본 정보 점검",
        },
        {
            "title": "네이버 스마트플레이스 소개",
            "url": "https://new.smartplace.naver.com/introduction/smartplace",
            "use": "업체 소개, 영업시간, 가격표, 리뷰, 통계, 스마트콜, 예약/주문, 톡톡 관리 항목 반영",
        },
        {
            "title": "네이버 스마트플레이스 공지: 범용 특화 컬렉션",
            "url": "https://smartplace.naver.com/notices/1018",
            "use": "업체 이미지, 방문자 리뷰, 예약/쿠폰/접근성 필터 노출에 맞춘 프로필 감사 항목 반영",
        },
        {
            "title": "네이버 스마트플레이스 Q&A: 검색 키워드 포함 가능성",
            "url": "https://new.smartplace.naver.com/notices/703",
            "use": "풍부한 업체정보가 다양한 이용자 검색 키워드 포함 가능성을 높인다는 기준을 추적 확장에 반영",
        },
        {
            "title": "네이버 스마트플레이스 방문자리뷰 어뷰징 페널티 기준",
            "url": "https://help.naver.com/service/30026/contents/25088?lang=ko",
            "use": "가짜 영수증, 허위 예약, 리워드 리뷰, 별점/문구 강요를 실행 금지 수단으로 차단",
        },
        {
            "title": "네이버 스마트플레이스 업체정보 작성 기준",
            "url": "https://smartplace.naver.com/help/policy?menu=modify",
            "use": "업체명·주소·지역명·상업 키워드 반복 삽입을 금지하고 실제 사업자 정보 중심으로 감사",
        },
        {
            "title": "네이버 서치어드바이저 웹 콘텐츠 스팸사례",
            "url": "https://searchadvisor.naver.com/guide/content-abusing",
            "use": "상위노출 목적의 스팸성 SEO, 백링크 악용, 리다이렉트/도메인 포워딩을 차단",
        },
        {
            "title": "네이버 서치어드바이저 사이트 최적화 리포트",
            "url": "https://searchadvisor.naver.com/guide/report-seo",
            "use": "연결 웹페이지의 제목·설명·robots·사이트맵·콘텐츠 품질을 플레이스 보조 신호 점검에 반영",
        },
        {
            "title": "네이버 서치어드바이저 IndexNow",
            "url": "https://searchadvisor.naver.com/guide/indexnow-about",
            "use": "새 FAQ/랜딩 업데이트 후 네이버에 변경 사실을 알리되 색인 보장 수단으로 오인하지 않도록 측정",
        },
        {
            "title": "네이버 스마트플레이스 새로오픈했어요 노출 조건",
            "url": "https://help.naver.com/service/30026/contents/20512",
            "use": "신규 업체는 개업일·가격정보·업체사진 등 필수 정보 누락 여부를 별도 점검",
        },
        {
            "title": "네이버 스마트플레이스 업체 정보 수정 방법",
            "url": "https://help.naver.com/service/30026/contents/20379?lang=ko",
            "use": "대표키워드 최대 5개, 부가정보, 휴무일·영업시간, 메뉴/질병명 정보 수정 루틴에 반영",
        },
        {
            "title": "네이버 스마트플레이스 업체 이미지 노출 기준",
            "url": "https://help.naver.com/service/30026/contents/20429?lang=ko",
            "use": "업주 등록 이미지 우선 노출과 상단 노출 최소 이미지 조건을 사진 감사 항목에 반영",
        },
        {
            "title": "네이버 스마트플레이스 AI 롱테일 검색 기능",
            "url": "https://help.naver.com/service/30026/contents/25167?lang=ko&osType=COMMONOS",
            "use": "Pathfinder 롱테일 의도를 업체정보·블로그/방문자 리뷰·이미지 의미 매칭 준비도로 전환",
        },
        {
            "title": "네이버 스마트플레이스 AI 브리핑 노출 안내",
            "url": "https://help.naver.com/service/30026/contents/24632?osType=COMMONOS",
            "use": "AI 브리핑은 이용자 작성 데이터를 바탕으로 하므로 리뷰/정보 품질 루프와 미노출 검토 기준에 반영",
        },
    ]

    PLACE_QUERY_STOPWORDS = {
        "비용",
        "가격",
        "후기",
        "추천",
        "근처",
        "주변",
        "가까운",
        "잘하는곳",
        "잘하는",
        "곳",
        "예약",
        "주차",
        "야간",
        "일요일",
        "주말",
        "가능",
        "방법",
        "기간",
    }

    PLACE_QUERY_INTENT_MODIFIERS: List[Dict[str, Any]] = [
        {
            "modifier": "주차",
            "metric": "access_convenience_score",
            "reason": "방문 편의 의도 키워드는 지도/플레이스 행동 전환과 연결됩니다.",
        },
        {
            "modifier": "예약",
            "metric": "availability_intent_score",
            "reason": "예약 가능성 의도는 플레이스 예약/문의 버튼 노출 점검과 연결됩니다.",
        },
        {
            "modifier": "비용",
            "metric": "payment_coverage_score",
            "reason": "비용/보험 의도는 상세설명, 가격표, FAQ 정합성 점검과 연결됩니다.",
        },
        {
            "modifier": "후기",
            "metric": "review_surface_score",
            "reason": "후기 의도는 실방문 리뷰와 답글 품질 루프 점검과 연결됩니다.",
        },
        {
            "modifier": "잘하는곳",
            "metric": "business_value_score",
            "reason": "상업적 선택 의도 키워드는 경쟁사 격차와 정보 충실도 점검에 필요합니다.",
        },
    ]

    PLACE_PROFILE_AUDIT_FIELDS: List[Dict[str, Any]] = [
        {
            "field": "업체명·업종·대표키워드",
            "rank_signal": "keyword_relevance",
            "priority": "high",
            "why": "검색어와 업체 정보의 유사도, 업종 정합성의 기본 항목입니다.",
            "checks": [
                "사업자/간판명과 다른 홍보성 수식어 제거",
                "대표키워드 5개가 실제 진료/서비스명과 일치하는지 확인",
                "무관한 지역명·증상명 반복 삽입 제거",
            ],
        },
        {
            "field": "상세설명·메뉴/서비스·가격표",
            "rank_signal": "information_completeness",
            "priority": "high",
            "why": "사용자가 찾는 서비스가 실제 제공 항목으로 설명되어야 합니다.",
            "checks": [
                "핵심 서비스별 설명, 대상, 방문 전 확인사항을 최신화",
                "가격/비용/보험 안내는 확인 가능한 범위로만 작성",
                "블로그/FAQ 문구와 스마트플레이스 설명의 충돌 제거",
            ],
        },
        {
            "field": "영업시간·휴무·예약/주문·톡톡",
            "rank_signal": "freshness_and_trend",
            "priority": "high",
            "why": "운영 정보와 예약 가능 정보는 방문 전 행동 전환에 직접 연결됩니다.",
            "checks": [
                "임시 휴무, 공휴일, 야간/주말 운영 상태 점검",
                "예약 가능 여부와 실제 접수 흐름 일치 여부 확인",
                "톡톡/전화/스마트콜 미응답 루프 점검",
            ],
        },
        {
            "field": "주소·지도핀·찾아오는 길·주차/접근성",
            "rank_signal": "local_content_alignment",
            "priority": "high",
            "why": "지도 검색은 거리와 방문 편의 정보의 영향을 크게 받습니다.",
            "checks": [
                "지도핀, 주소, 건물명, 층수, 입구 설명 확인",
                "주차, 대중교통, 휠체어/유모차 접근 가능 여부 최신화",
                "찾아오는 길 설명과 숏폼/블로그 방문 동선 일치 확인",
            ],
        },
        {
            "field": "업체 사진·대표 이미지·방문자 리뷰 이미지",
            "rank_signal": "information_completeness",
            "priority": "medium",
            "why": "최근 검색 결과 개편은 업체 이미지와 리뷰 이미지 노출 비중을 높이고 있습니다.",
            "checks": [
                "업체 기본정보 사진이 최근 외관/내부/동선을 보여주는지 확인",
                "대표 이미지가 PC/모바일에서 잘리지 않는지 확인",
                "부적절한 방문자 리뷰 이미지는 정상 신고 절차만 사용",
            ],
        },
        {
            "field": "실방문 리뷰·답글·반복 질문",
            "rank_signal": "authentic_visit_feedback",
            "priority": "medium",
            "why": "리뷰는 신뢰 신호지만 조작은 업체 단위 페널티 위험입니다.",
            "checks": [
                "실제 방문 고객에게만 자율 리뷰 안내",
                "별점, 문구, 긍정 표현, 보상을 조건으로 요구하지 않음",
                "반복 질문을 FAQ와 상세설명 개선으로 전환",
            ],
        },
        {
            "field": "홈페이지·블로그·새소식·서치어드바이저",
            "rank_signal": "local_content_alignment",
            "priority": "medium",
            "why": "플레이스와 연결된 콘텐츠가 같은 지역·서비스 의도를 설명해야 합니다.",
            "checks": [
                "홈페이지/랜딩 제목, 설명, robots 차단 상태 점검",
                "블로그 새소식과 스마트플레이스 설명의 서비스명 통일",
                "핵심 키워드 콘텐츠 발행 후 색인/노출 여부 확인",
            ],
        },
    ]

    def __init__(self, db_path: str):
        self.db_path = str(db_path)

    def build_user_brief(
        self,
        *,
        limit: int = 12,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
        use_codex: bool = False,
    ) -> Dict[str, Any]:
        cards = self.keyword_cards(
            limit=limit,
            business_core_only=business_core_only,
            latest_verified_only=latest_verified_only,
        )
        metrics = self._brief_metrics(cards)
        place_tracking = self._place_tracking_summary(cards, metrics)
        place_rank_lift = self._place_rank_lift_plan(cards, metrics, place_tracking)
        self._attach_place_lift_context(cards, place_rank_lift)
        place_value_loop = self._place_value_loop(cards, metrics, place_tracking, place_rank_lift)
        self._attach_place_value_context(cards, place_value_loop)
        action_queue = self._build_action_queue(cards)
        summary = self._build_summary(cards, metrics, place_tracking)
        top_insights = self._build_top_insights(
            cards,
            metrics,
            place_tracking,
            place_rank_lift,
            place_value_loop,
        )
        agent_handoffs = self.build_agent_handoffs(cards=cards)
        prompt_context = self.format_prompt_context(
            cards=cards,
            agent="all",
            place_value_loop=place_value_loop,
        )
        codex_synthesis = self._codex_synthesis(
            cards=cards,
            metrics=metrics,
            place_tracking=place_tracking,
            place_rank_lift=place_rank_lift,
            place_value_loop=place_value_loop,
            action_queue=action_queue,
            requested=use_codex,
        )
        provenance = self._build_provenance(
            cards,
            latest_verified_only=latest_verified_only,
            business_core_only=business_core_only,
        )
        quality_gate = self._quality_gate(cards, metrics)
        feedback_summary = self._feedback_summary(cards)
        decision_overview = self._decision_overview(cards)

        return {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "pathfinder",
            "audience": "user",
            "summary": summary,
            "top_insights": top_insights,
            "codex_synthesis": codex_synthesis,
            "provenance": provenance,
            "place_tracking": place_tracking,
            "place_rank_lift": place_rank_lift,
            "place_value_loop": place_value_loop,
            "quality_gate": quality_gate,
            "feedback_summary": feedback_summary,
            "decision_overview": decision_overview,
            "delivery_contract": self._delivery_contract(),
            "feedback_contract": self._feedback_contract(),
            "action_queue": action_queue,
            "keyword_cards": cards,
            "agent_handoffs": agent_handoffs,
            "codex_prompt_context": prompt_context,
            "metrics": metrics,
        }

    def build_agent_handoffs(
        self,
        *,
        cards: Optional[List[Dict[str, Any]]] = None,
        agent: str = "all",
        limit: int = 8,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
    ) -> Dict[str, Any]:
        if cards is None:
            cards = self.keyword_cards(
                limit=limit,
                business_core_only=business_core_only,
                latest_verified_only=latest_verified_only,
            )
        selected = cards[:limit]
        place_rank_lift = self._ensure_place_lift_context(selected)
        self._ensure_place_value_context(selected, place_rank_lift=place_rank_lift)
        requested = AGENT_ALIASES.get(agent, agent)
        packets = {
            "blog_agent": self._blog_packet(selected),
            "shorts_studio_agent": self._shorts_packet(selected),
            "viral_hunter_agent": self._viral_packet(selected),
            "ad_agent": self._ad_packet(selected),
        }
        if requested != "all":
            packets = {requested: packets.get(requested, {"tasks": [], "prompt_context": ""})}
        return {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "pathfinder",
            "agent": requested,
            "feedback_summary": self._feedback_summary(selected),
            "decision_overview": self._decision_overview(selected),
            "packets": packets,
        }

    def export_user_brief(self, output_path: str, **kwargs: Any) -> Dict[str, Any]:
        brief = self.build_user_brief(**kwargs)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        return brief

    def keyword_cards(
        self,
        *,
        limit: int = 12,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_keywords(
            limit=max(1, min(int(limit), 100)),
            business_core_only=business_core_only,
            latest_verified_only=latest_verified_only,
        )
        cards = [self._row_to_card(row) for row in rows]
        cards.sort(key=lambda item: item["insight_score"], reverse=True)
        selected = cards[:limit]
        self._attach_place_rank_snapshots(selected)
        self._attach_feedback_snapshots(selected)
        return selected

    def format_prompt_context(
        self,
        *,
        cards: Optional[Sequence[Dict[str, Any]]] = None,
        agent: str = "all",
        topic: Optional[str] = None,
        limit: int = 5,
        place_value_loop: Optional[Dict[str, Any]] = None,
    ) -> str:
        if cards is None:
            cards = self.keyword_cards(limit=limit)
        selected = list(cards)[:limit]
        place_rank_lift = self._ensure_place_lift_context(selected)
        place_value_loop = place_value_loop or self._ensure_place_value_context(
            selected,
            place_rank_lift=place_rank_lift,
        )
        lines = [
            "[Pathfinder Insight Handoff]",
            f"- Agent: {agent}",
            f"- Topic filter: {topic or 'none'}",
            "- Use these as evidence-backed campaign inputs, not as generic keyword stuffing.",
        ]
        if place_rank_lift:
            expansion = place_rank_lift.get("tracking_expansion") or {}
            candidates = expansion.get("candidate_keywords") or []
            lines.append(
                f"- Place rank lift: {place_rank_lift.get('headline')} | "
                f"actions={place_rank_lift.get('priority_action_count', 0)} | "
                f"tracking_candidates={len(candidates)}"
            )
            if candidates:
                lines.append(
                    "- Place tracking candidates: "
                    + ", ".join(str(item.get("keyword")) for item in candidates[:5])
                )
        if place_value_loop:
            rep_keywords = (place_value_loop.get("pathfinder_to_place") or {}).get("representative_keyword_candidates") or []
            lines.append(
                f"- Place value loop: {place_value_loop.get('headline')} | "
                f"representative_keywords={len(rep_keywords)} | "
                f"reverse_signals={len((place_value_loop.get('place_to_pathfinder') or {}).get('import_signals') or [])}"
            )
            if rep_keywords:
                lines.append(
                    "- SmartPlace representative keyword candidates: "
                    + ", ".join(str(item.get("keyword")) for item in rep_keywords[:5])
                )
        for idx, card in enumerate(selected, 1):
            metrics = card["metrics"]
            lines.append(
                f"{idx}. {card['keyword']} | id={card.get('handoff_id', '')} | grade={card['grade']} | "
                f"confidence={card.get('confidence_band', 'unknown')}:{card.get('confidence', 0)} | "
                f"business={metrics['business_value_score']:.0f} | volume={metrics['search_volume']} | "
                f"intent={card['search_intent']} | reasons={', '.join(card['why_it_matters'][:4])}"
            )
            evidence = [
                f"{item.get('signal')}={item.get('value')}"
                for item in card.get("evidence_trace", [])[:4]
            ]
            if evidence:
                lines.append(f"   - Evidence: {', '.join(evidence)}")
            decision = card.get("decision_packet") or {}
            if decision:
                lines.append(
                    f"   - Decision: {decision.get('state')} | policy={decision.get('publish_policy')} | "
                    f"reasons={', '.join(decision.get('reason_codes') or [])}"
                )
            data_quality = card.get("data_quality") or {}
            if data_quality:
                lines.append(
                    f"   - Data quality: {data_quality.get('status')}:{data_quality.get('score')} | "
                    f"warnings={', '.join(data_quality.get('warnings') or [])}"
                )
            measurement = card.get("measurement_plan") or {}
            if measurement:
                lines.append(f"   - Measure: {measurement.get('primary_metric')}")
            if card.get("human_review", {}).get("required"):
                lines.append(
                    "   - Human review: "
                    + ", ".join(card.get("human_review", {}).get("reasons", []))
                )
            feedback = card.get("feedback_snapshot") or {}
            if feedback.get("total_events"):
                lines.append(
                    f"   - Feedback: {feedback.get('learning_status')} "
                    f"{json.dumps(feedback.get('counts') or {}, ensure_ascii=False)}"
                )
            place = card.get("place_rank") or {}
            if place.get("tracked"):
                current = place.get("current") or {}
                rank_label = current.get("rank") if current.get("rank") else current.get("status", "unknown")
                lines.append(
                    f"   - Place rank: {rank_label} | device={current.get('device_type', 'unknown')} | "
                    f"trend={place.get('trend', 'unknown')} | delta={place.get('rank_delta')}"
                )
            lift_actions = card.get("place_lift_actions") or []
            if lift_actions:
                primary_lift = lift_actions[0]
                lines.append(
                    f"   - Place lift: {primary_lift.get('title')} | "
                    f"measure={primary_lift.get('measurement')}"
                )
            tracking_candidates = card.get("place_tracking_candidates") or []
            if tracking_candidates:
                lines.append(
                    "   - Place tracking candidates: "
                    + ", ".join(str(item.get("keyword")) for item in tracking_candidates[:3])
                )
            value_brief = card.get("place_value_brief") or {}
            if value_brief:
                lines.append(
                    f"   - Place value: {value_brief.get('profile_message')} | "
                    f"field={value_brief.get('smartplace_field')}"
                )
            if card["agent_notes"].get(agent):
                lines.append(f"   - Agent note: {card['agent_notes'][agent]}")
            elif agent == "all":
                lines.append(f"   - Blog: {card['agent_notes']['blog_agent']}")
                lines.append(f"   - Shorts: {card['agent_notes']['shorts_studio_agent']}")
            if card["risks"]:
                lines.append(f"   - Guardrails: {', '.join(card['risks'])}")
        return "\n".join(lines)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _columns(self, cursor: sqlite3.Cursor, table: str = "keyword_insights") -> set[str]:
        return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}

    def _latest_completed_run_id(self, cursor: sqlite3.Cursor) -> Optional[int]:
        if not self._table_exists(cursor, "scan_runs"):
            return None
        try:
            columns = self._columns(cursor, "scan_runs")
            lineage_filters = []
            if "scan_type" in columns:
                lineage_filters.append("scan_type = 'legion'")
            if "mode" in columns:
                lineage_filters.append("mode LIKE '%legion%'")
            if not lineage_filters:
                return None
            completed_order = "completed_at DESC, id DESC" if "completed_at" in columns else "id DESC"
            row = cursor.execute(
                f"""
                SELECT id
                FROM scan_runs
                WHERE status = 'completed'
                  AND ({" OR ".join(lineage_filters)})
                ORDER BY {completed_order}
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return int(row[0]) if row else None

    def _select_expr(self, column: str, columns: set[str], alias: str = "ki") -> str:
        default = self.TEXT_DEFAULTS.get(column, self.NUMERIC_DEFAULTS.get(column, 0))
        if column == "last_scan_run_id" and column not in columns and "scan_run_id" in columns:
            return f"COALESCE({alias}.scan_run_id, {_literal(default)}) AS {column}"
        if column in columns:
            return f"COALESCE({alias}.{column}, {_literal(default)}) AS {column}"
        return f"{_literal(default)} AS {column}"

    def _fetch_keywords(
        self,
        *,
        limit: int,
        business_core_only: bool,
        latest_verified_only: bool,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "keyword_insights"):
                return []
            columns = self._columns(cursor)
            text_cols = list(self.TEXT_DEFAULTS)
            numeric_cols = list(self.NUMERIC_DEFAULTS)
            select_cols = [self._select_expr(col, columns) for col in text_cols + numeric_cols]
            filters = ["1=1"]
            params: List[Any] = []

            if "status" in columns:
                filters.append("COALESCE(ki.status, 'active') != 'archived'")
            if "document_count" in columns:
                filters.append("COALESCE(ki.document_count, 0) > 0")
            if business_core_only and "business_core" in columns:
                filters.append("COALESCE(ki.business_core, 0) = 1")
            if latest_verified_only and ("last_scan_run_id" in columns or "scan_run_id" in columns):
                latest_run_id = self._latest_completed_run_id(cursor)
                if latest_run_id:
                    if "last_scan_run_id" in columns and "scan_run_id" in columns:
                        filters.append("COALESCE(ki.last_scan_run_id, ki.scan_run_id, 0) = ?")
                    elif "last_scan_run_id" in columns:
                        filters.append("COALESCE(ki.last_scan_run_id, 0) = ?")
                    else:
                        filters.append("COALESCE(ki.scan_run_id, 0) = ?")
                    params.append(latest_run_id)

            order_terms = []
            for column, direction in (
                ("high_value_longtail", "DESC"),
                ("business_value_score", "DESC"),
                ("priority_v3", "DESC"),
                ("opportunity", "DESC"),
                ("search_volume", "DESC"),
            ):
                if column in columns:
                    order_terms.append(f"COALESCE(ki.{column}, 0) {direction}")
            order_clause = ", ".join(order_terms) or "ki.keyword ASC"

            params.append(limit)
            cursor.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM keyword_insights ki
                WHERE {" AND ".join(filters)}
                ORDER BY {order_clause}
                LIMIT ?
                """,
                params,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _own_place_terms(self) -> List[str]:
        terms = {"규림", "규림한의원"}
        profile_path = Path("config/business_profile.json")
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                business = profile.get("business") if isinstance(profile.get("business"), dict) else profile
                for key in ("name", "short_name", "english_name"):
                    value = str((business or {}).get(key) or "").strip()
                    if value:
                        terms.add(value)
            except Exception:
                pass
        return [re.sub(r"\s+", "", term.lower()) for term in terms if term]

    def _is_own_place_target(self, target_name: str, own_terms: Sequence[str]) -> bool:
        compact = re.sub(r"\s+", "", (target_name or "").lower())
        return bool(compact and any(term and term in compact for term in own_terms))

    def _fetch_place_rank_rows(self, keywords: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
        requested = [keyword for keyword in keywords if keyword]
        if not requested:
            return {}
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "rank_history"):
                return {}
            columns = self._columns(cursor, "rank_history")
            if "keyword" not in columns:
                return {}
            select_cols = [
                self._select_expr("keyword", columns, alias="rh"),
                self._select_expr("rank", columns, alias="rh"),
                self._select_expr("target_name", columns, alias="rh"),
                self._select_expr("status", columns, alias="rh"),
                self._select_expr("total_results", columns, alias="rh"),
                self._select_expr("note", columns, alias="rh"),
                self._select_expr("device_type", columns, alias="rh"),
            ]
            checked_expr = "rh.checked_at" if "checked_at" in columns else ("rh.date" if "date" in columns else "NULL")
            date_expr = "rh.date" if "date" in columns else checked_expr
            select_cols.append(f"COALESCE({checked_expr}, {date_expr}, '') AS checked_at")
            if "id" in columns:
                order_clause = f"COALESCE({checked_expr}, {date_expr}, '') DESC, rh.id DESC"
            else:
                order_clause = f"COALESCE({checked_expr}, {date_expr}, '') DESC"

            placeholders = ", ".join("?" for _ in requested)
            rows = cursor.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM rank_history rh
                WHERE rh.keyword IN ({placeholders})
                ORDER BY rh.keyword ASC, {order_clause}
                LIMIT 2000
                """,
                requested,
            ).fetchall()
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                data = dict(row)
                grouped.setdefault(str(data.get("keyword") or ""), []).append(data)
            return grouped
        except sqlite3.OperationalError:
            return {}
        finally:
            conn.close()

    def _fetch_recent_place_rank_rows(self, limit: int = 500) -> Dict[str, List[Dict[str, Any]]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "rank_history"):
                return {}
            columns = self._columns(cursor, "rank_history")
            if "keyword" not in columns:
                return {}
            select_cols = [
                self._select_expr("keyword", columns, alias="rh"),
                self._select_expr("rank", columns, alias="rh"),
                self._select_expr("target_name", columns, alias="rh"),
                self._select_expr("status", columns, alias="rh"),
                self._select_expr("total_results", columns, alias="rh"),
                self._select_expr("note", columns, alias="rh"),
                self._select_expr("device_type", columns, alias="rh"),
            ]
            checked_expr = "rh.checked_at" if "checked_at" in columns else ("rh.date" if "date" in columns else "NULL")
            date_expr = "rh.date" if "date" in columns else checked_expr
            select_cols.append(f"COALESCE({checked_expr}, {date_expr}, '') AS checked_at")
            order_clause = f"COALESCE({checked_expr}, {date_expr}, '') DESC"
            if "id" in columns:
                order_clause += ", rh.id DESC"

            rows = cursor.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM rank_history rh
                ORDER BY {order_clause}
                LIMIT ?
                """,
                (max(1, min(int(limit), 5000)),),
            ).fetchall()
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                data = dict(row)
                grouped.setdefault(str(data.get("keyword") or ""), []).append(data)
            return grouped
        except sqlite3.OperationalError:
            return {}
        finally:
            conn.close()

    def _rank_row_snapshot(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rank": _as_int(row.get("rank")),
            "status": row.get("status") or "unknown",
            "target_name": row.get("target_name") or "",
            "device_type": row.get("device_type") or "unknown",
            "checked_at": row.get("checked_at") or "",
            "total_results": _as_int(row.get("total_results")),
            "note": row.get("note") or "",
        }

    def _visibility_state(self, current: Optional[Dict[str, Any]]) -> str:
        if not current:
            return "untracked"
        status = current.get("status") or "unknown"
        rank = _as_int(current.get("rank"))
        if status != "found" or rank <= 0:
            return status if status in {"not_in_results", "no_results", "error"} else "not_found"
        if rank <= 3:
            return "top3"
        if rank <= 10:
            return "top10"
        return "visible"

    def _place_rank_snapshot_for_keyword(
        self,
        rows: Sequence[Dict[str, Any]],
        own_terms: Sequence[str],
    ) -> Dict[str, Any]:
        if not rows:
            return {
                "tracked": False,
                "visibility_state": "untracked",
                "trend": "untracked",
                "current": None,
                "previous": None,
                "rank_delta": None,
                "devices": {},
                "best_competitor": None,
                "competitor_gap": None,
                "latest_checked_at": None,
            }

        own_rows = [row for row in rows if self._is_own_place_target(str(row.get("target_name") or ""), own_terms)]
        competitor_rows = [row for row in rows if row not in own_rows]

        by_device: Dict[str, List[Dict[str, Any]]] = {}
        for row in own_rows:
            by_device.setdefault(str(row.get("device_type") or "unknown"), []).append(row)
        devices = {
            device: self._rank_row_snapshot(device_rows[0])
            for device, device_rows in by_device.items()
            if device_rows
        }

        current_row = None
        if by_device.get("mobile"):
            current_row = by_device["mobile"][0]
        elif by_device:
            current_row = next(iter(by_device.values()))[0]
        current = self._rank_row_snapshot(current_row) if current_row else None

        previous = None
        if current_row:
            current_device = str(current_row.get("device_type") or "unknown")
            current_target = str(current_row.get("target_name") or "")
            for row in by_device.get(current_device, [])[1:]:
                if str(row.get("target_name") or "") == current_target:
                    previous = self._rank_row_snapshot(row)
                    break

        best_competitor = None
        latest_competitors: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in competitor_rows:
            key = (str(row.get("target_name") or ""), str(row.get("device_type") or "unknown"))
            if key not in latest_competitors:
                latest_competitors[key] = row
        found_competitors = [
            self._rank_row_snapshot(row)
            for row in latest_competitors.values()
            if (row.get("status") or "unknown") == "found" and _as_int(row.get("rank")) > 0
        ]
        if found_competitors:
            best_competitor = min(found_competitors, key=lambda item: item["rank"])

        rank_delta = None
        trend = "untracked"
        if current:
            status = current.get("status") or "unknown"
            rank = _as_int(current.get("rank"))
            prev_rank = _as_int((previous or {}).get("rank"))
            if status != "found" or rank <= 0:
                trend = status if status in {"not_in_results", "no_results", "error"} else "not_found"
            elif previous and prev_rank > 0:
                rank_delta = prev_rank - rank
                if rank_delta > 0:
                    trend = "improved"
                elif rank_delta < 0:
                    trend = "declined"
                else:
                    trend = "stable"
            else:
                trend = "new"

        competitor_gap = None
        if current and best_competitor and current.get("status") == "found" and _as_int(current.get("rank")) > 0:
            competitor_gap = _as_int(current.get("rank")) - _as_int(best_competitor.get("rank"))

        latest_checked_at = current.get("checked_at") if current else None
        if not latest_checked_at and rows:
            latest_checked_at = str(rows[0].get("checked_at") or "")

        return {
            "tracked": bool(current),
            "visibility_state": self._visibility_state(current),
            "trend": trend,
            "current": current,
            "previous": previous,
            "rank_delta": rank_delta,
            "devices": devices,
            "best_competitor": best_competitor,
            "competitor_gap": competitor_gap,
            "latest_checked_at": latest_checked_at,
        }

    def _attach_place_rank_snapshots(self, cards: Sequence[Dict[str, Any]]) -> None:
        if not cards:
            return
        rank_rows = self._fetch_place_rank_rows([card.get("keyword", "") for card in cards])
        own_terms = self._own_place_terms()
        for card in cards:
            snapshot = self._place_rank_snapshot_for_keyword(
                rank_rows.get(str(card.get("keyword") or ""), []),
                own_terms,
            )
            card["place_rank"] = snapshot
            current = snapshot.get("current") or {}
            if snapshot.get("tracked"):
                if current.get("status") == "found" and current.get("rank"):
                    card.setdefault("evidence_trace", []).append({
                        "signal": "place_current_rank",
                        "value": current.get("rank"),
                        "threshold": "tracked",
                        "source": "rank_history",
                        "meaning": "latest Naver Place rank was collected after place tracking",
                    })
                    if snapshot.get("rank_delta") is not None:
                        card.setdefault("evidence_trace", []).append({
                            "signal": "place_rank_delta",
                            "value": snapshot.get("rank_delta"),
                            "threshold": 0,
                            "source": "rank_history",
                            "meaning": "positive means the place rank improved from the previous scan",
                        })
                else:
                    card.setdefault("evidence_trace", []).append({
                        "signal": "place_visibility_status",
                        "value": current.get("status") or snapshot.get("trend"),
                        "threshold": "tracked",
                        "source": "rank_history",
                        "meaning": "latest place tracking did not find the clinic in visible results",
                    })
                if snapshot.get("competitor_gap") is not None and snapshot.get("competitor_gap") > 0:
                    card.setdefault("evidence_trace", []).append({
                        "signal": "place_competitor_gap",
                        "value": snapshot.get("competitor_gap"),
                        "threshold": 1,
                        "source": "rank_history",
                        "meaning": "a competitor currently ranks ahead on the same keyword",
                    })
                card["evidence_trace"] = card.get("evidence_trace", [])[:18]

                reasons = list(card.get("why_it_matters") or [])
                if snapshot.get("trend") == "declined":
                    reasons.append("플레이스 순위가 직전 추적 대비 하락")
                elif snapshot.get("trend") == "improved":
                    reasons.append("플레이스 순위가 직전 추적 대비 상승")
                elif snapshot.get("visibility_state") in {"not_in_results", "no_results", "not_found", "error"}:
                    reasons.append("플레이스 최신 추적에서 노출 회복 필요")
                if snapshot.get("competitor_gap") is not None and snapshot.get("competitor_gap") > 0:
                    reasons.append("동일 키워드에서 경쟁사가 앞섬")
                card["why_it_matters"] = list(dict.fromkeys(reasons))[:8]
            else:
                card.setdefault("place_rank", snapshot)

    def _row_to_card(self, row: Dict[str, Any]) -> Dict[str, Any]:
        quality_flags = _json_list(row.get("quality_flags_json"))
        source_signals = _json_list(row.get("source_signals_json"))
        reasons = self._why_it_matters(row, quality_flags, source_signals)
        risks = self._risks(row, quality_flags)
        evidence_trace = self._evidence_trace(row, quality_flags, source_signals)
        confidence = self._confidence(row, evidence_trace, risks, source_signals)
        human_review = self._human_review(row, risks, confidence, evidence_trace)
        data_quality = self._data_quality_snapshot(row, evidence_trace, quality_flags, source_signals)
        decision_packet = self._decision_packet(row, confidence, human_review, data_quality, risks)
        measurement_plan = self._measurement_plan(row, decision_packet)
        handoff_id = self._handoff_id(row, evidence_trace)
        agent_notes = self._agent_notes(row, reasons, risks)
        actions = self._keyword_actions(row, reasons, risks)
        metrics = {
            key: _as_float(row.get(key))
            for key in self.NUMERIC_DEFAULTS
            if key not in {"business_core", "high_value_longtail"}
        }
        metrics["search_volume"] = _as_int(row.get("search_volume"))
        metrics["document_count"] = _as_int(row.get("document_count"))

        score = self._insight_score(row, reasons, risks)
        return {
            "handoff_id": handoff_id,
            "keyword": row.get("keyword", ""),
            "category": row.get("category") or "기타",
            "grade": row.get("grade") or "C",
            "search_intent": row.get("search_intent") or "unknown",
            "trend_status": row.get("trend_status") or "unknown",
            "content_cluster_key": row.get("content_cluster_key") or "",
            "insight_score": round(score, 2),
            "confidence": confidence,
            "confidence_band": self._confidence_band(confidence),
            "why_it_matters": reasons,
            "risks": risks,
            "evidence_trace": evidence_trace,
            "human_review": human_review,
            "data_quality": data_quality,
            "decision_packet": decision_packet,
            "measurement_plan": measurement_plan,
            "quality_flags": quality_flags,
            "source_signals": source_signals,
            "provenance": {
                "source_table": "keyword_insights",
                "source": row.get("source") or "pathfinder",
                "last_scan_run_id": _as_int(row.get("last_scan_run_id")),
                "created_at": row.get("created_at") or "",
                "updated_at": row.get("updated_at") or "",
            },
            "metrics": metrics,
            "signals": {
                "high_value_longtail": bool(_as_int(row.get("high_value_longtail"))),
                "preferred_search_surface": row.get("preferred_search_surface") or "",
                "recommended_content_type": row.get("recommended_content_type") or "",
                "availability_intent_type": row.get("availability_intent_type") or "none",
                "payment_coverage_type": row.get("payment_coverage_type") or "none",
                "access_convenience_type": row.get("access_convenience_type") or "none",
                "review_intent_type": row.get("review_intent_type") or "none",
                "brand_intent_type": row.get("brand_intent_type") or "generic",
            },
            "agent_notes": agent_notes,
            "recommended_actions": actions,
        }

    def _confidence_band(self, confidence: float) -> str:
        if confidence >= 0.78:
            return "high"
        if confidence >= 0.58:
            return "medium"
        return "low"

    def _evidence_trace(
        self,
        row: Dict[str, Any],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> List[Dict[str, Any]]:
        evidence: List[Dict[str, Any]] = []

        def add_score(signal: str, threshold: float, meaning: str, source: str = "keyword_insights") -> None:
            value = _as_float(row.get(signal))
            if value >= threshold:
                evidence.append({
                    "signal": signal,
                    "value": round(value, 2),
                    "threshold": threshold,
                    "source": source,
                    "meaning": meaning,
                })

        if _as_int(row.get("high_value_longtail")):
            evidence.append({
                "signal": "high_value_longtail",
                "value": True,
                "threshold": True,
                "source": "keyword_insights",
                "meaning": "business value and long-tail specificity passed the Legion gate",
            })
        add_score("business_value_score", 70, "commercial or conversion value is strong")
        add_score("longtail_score", 70, "query is specific enough to carry long-tail intent")
        add_score("local_surface_score", 70, "local/place exposure is a meaningful surface")
        add_score("profile_action_signal", 60, "profile action or visit signal is present")
        add_score("availability_intent_score", 70, "reservation or availability intent is explicit")
        add_score("payment_coverage_score", 70, "cost, insurance, or document intent is explicit")
        add_score("access_convenience_score", 70, "parking, route, or access convenience intent is explicit")
        add_score("review_surface_score", 70, "review or reputation comparison intent is explicit")
        add_score("community_signal", 40, "community demand signal is present")
        add_score("conversion_signal", 35, "conversion-like behavior signal is present")
        add_score("verification_score", 65, "external verification score is strong")
        add_score("novelty_score", 65, "keyword is meaningfully differentiated from common terms")

        mobile_share = _as_float(row.get("mobile_share"))
        if mobile_share >= 0.65:
            evidence.append({
                "signal": "mobile_share",
                "value": round(mobile_share, 3),
                "threshold": 0.65,
                "source": "keyword_insights",
                "meaning": "mobile-heavy search behavior supports short-form or local content",
            })
        if row.get("trend_status") == "rising":
            evidence.append({
                "signal": "trend_status",
                "value": "rising",
                "threshold": "rising",
                "source": "keyword_insights",
                "meaning": "trend movement supports near-term execution",
            })
        for signal in source_signals[:6]:
            evidence.append({
                "signal": "source_signal",
                "value": signal,
                "threshold": "observed",
                "source": "source_signals_json",
                "meaning": "the keyword was observed by an upstream research source",
            })
        for flag in quality_flags[:4]:
            evidence.append({
                "signal": "quality_flag",
                "value": flag,
                "threshold": "review",
                "source": "quality_flags_json",
                "meaning": "quality flag must be considered before execution",
            })
        return evidence[:18]

    def _confidence(
        self,
        row: Dict[str, Any],
        evidence_trace: Sequence[Dict[str, Any]],
        risks: Sequence[str],
        source_signals: Sequence[str],
    ) -> float:
        positive_evidence_count = sum(1 for item in evidence_trace if item.get("signal") != "quality_flag")
        source_diversity = len(set(source_signals))
        score = 0.42
        score += min(0.30, positive_evidence_count * 0.035)
        score += min(0.12, source_diversity * 0.035)
        score += min(0.08, _as_float(row.get("verification_score")) / 1000.0)
        score += min(0.05, _as_int(row.get("document_count")) / 10000.0)
        if _as_int(row.get("high_value_longtail")):
            score += 0.05
        if row.get("trend_status") == "rising":
            score += 0.03
        score -= min(0.14, len(risks) * 0.035)
        score -= min(0.10, _as_float(row.get("medical_ad_risk_score")) / 1000.0)
        score -= min(0.08, _as_float(row.get("competitor_brand_risk_score")) / 1100.0)
        return round(max(0.05, min(0.95, score)), 2)

    def _human_review(
        self,
        row: Dict[str, Any],
        risks: Sequence[str],
        confidence: float,
        evidence_trace: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        if confidence < 0.58:
            reasons.append("low_confidence")
        if len(evidence_trace) < 2:
            reasons.append("thin_evidence")
        if risks:
            reasons.append("guardrail_risk")
        if _as_float(row.get("medical_ad_risk_score")) >= 50:
            reasons.append("medical_ad_review")
        if _as_float(row.get("competitor_brand_risk_score")) >= 50:
            reasons.append("competitor_brand_review")
        if _as_float(row.get("reputation_risk_score")) >= 50:
            reasons.append("reputation_review")
        reasons = list(dict.fromkeys(reasons))
        return {
            "required": bool(reasons),
            "reasons": reasons,
            "recommended_owner": "operator" if reasons else "agent",
        }

    def _handoff_id(self, row: Dict[str, Any], evidence_trace: Sequence[Dict[str, Any]]) -> str:
        payload = {
            "keyword": row.get("keyword", ""),
            "category": row.get("category", ""),
            "grade": row.get("grade", ""),
            "last_scan_run_id": _as_int(row.get("last_scan_run_id")),
            "evidence": [
                {
                    "signal": item.get("signal"),
                    "value": item.get("value"),
                }
                for item in evidence_trace[:8]
            ],
        }
        digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"pf-{digest[:12]}"

    def _data_quality_snapshot(
        self,
        row: Dict[str, Any],
        evidence_trace: Sequence[Dict[str, Any]],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> Dict[str, Any]:
        required_values = {
            "keyword": bool(row.get("keyword")),
            "grade": bool(row.get("grade")),
            "category": bool(row.get("category")),
            "search_volume": _as_int(row.get("search_volume")) > 0,
            "document_count": _as_int(row.get("document_count")) > 0,
            "business_value_score": _as_float(row.get("business_value_score")) > 0,
            "longtail_score": _as_float(row.get("longtail_score")) > 0,
            "evidence_trace": bool(evidence_trace),
        }
        completeness = sum(1 for present in required_values.values() if present) / len(required_values)
        source_diversity = len(set(source_signals))
        has_recent_scan = _as_int(row.get("last_scan_run_id")) > 0
        warnings: List[str] = []
        if completeness < 0.75:
            warnings.append("missing_core_fields")
        if source_diversity < 2:
            warnings.append("single_or_missing_source_signal")
        if not has_recent_scan:
            warnings.append("scan_run_not_linked")
        if quality_flags:
            warnings.append("quality_flags_present")

        score = completeness * 0.55
        score += min(0.20, source_diversity * 0.07)
        score += 0.15 if has_recent_scan else 0.0
        score += min(0.10, len(evidence_trace) * 0.015)
        if quality_flags:
            score -= min(0.15, len(quality_flags) * 0.035)
        score = round(max(0.0, min(1.0, score)), 2)
        if score >= 0.78 and not warnings:
            status = "fit_for_action"
        elif score >= 0.58:
            status = "fit_with_caveats"
        else:
            status = "thin"
        return {
            "status": status,
            "score": score,
            "dimensions": {
                "completeness": round(completeness, 2),
                "source_diversity": source_diversity,
                "scan_run_linked": has_recent_scan,
                "evidence_items": len(evidence_trace),
                "quality_flag_count": len(quality_flags),
            },
            "warnings": warnings,
            "required_fields_present": required_values,
        }

    def _decision_packet(
        self,
        row: Dict[str, Any],
        confidence: float,
        human_review: Dict[str, Any],
        data_quality: Dict[str, Any],
        risks: Sequence[str],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        if confidence < 0.58:
            reasons.append("low_confidence")
        elif confidence < 0.78:
            reasons.append("medium_confidence")
        if human_review.get("required"):
            reasons.extend(human_review.get("reasons") or ["human_review_required"])
        if data_quality.get("status") == "thin":
            reasons.append("thin_data_quality")
        elif data_quality.get("warnings"):
            reasons.append("data_quality_caveat")
        if risks:
            reasons.append("guardrail_risk")

        if "low_confidence" in reasons or "thin_data_quality" in reasons:
            state = "hold"
        elif human_review.get("required") or risks or confidence < 0.78 or data_quality.get("warnings"):
            state = "review"
        else:
            state = "go"
        publish_policy = {
            "go": "agent_can_draft_and_operator_can_publish",
            "review": "agent_can_draft_operator_must_review",
            "hold": "operator_review_only",
        }[state]
        return {
            "state": state,
            "owner": "agent" if state == "go" else "operator",
            "publish_policy": publish_policy,
            "reason_codes": list(dict.fromkeys(reasons)),
            "primary_decision": self._primary_decision(row),
        }

    def _primary_decision(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "publish access-convenience content only if route/parking details are verified"
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "publish FAQ content only if cost, insurance, and document claims are verified"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "publish reservation-focused content only if availability wording is current"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "publish selection-criteria content without review manipulation"
        return "draft intent-matched content with evidence and guardrails preserved"

    def _measurement_plan(self, row: Dict[str, Any], decision_packet: Dict[str, Any]) -> Dict[str, Any]:
        keyword = row.get("keyword", "")
        if _as_float(row.get("access_convenience_score")) >= 70:
            primary_metric = "visit-inquiry or profile-action feedback for access convenience content"
        elif _as_float(row.get("payment_coverage_score")) >= 70:
            primary_metric = "consultation inquiry after cost/insurance FAQ engagement"
        elif _as_float(row.get("availability_intent_score")) >= 70:
            primary_metric = "reservation or availability-check inquiry"
        elif _as_float(row.get("review_surface_score")) >= 70:
            primary_metric = "inquiry after selection-criteria or reputation-safety content"
        else:
            primary_metric = "accepted or completed Pathfinder handoff feedback"
        review_after_days = 14 if row.get("trend_status") == "rising" else 30
        return {
            "hypothesis": f"{keyword} will create higher-quality intent-matched demand than a generic head keyword.",
            "primary_metric": primary_metric,
            "secondary_metrics": [
                "accepted/completed feedback on the handoff_id",
                "needs_review/rejected/failed feedback ratio",
                "Naver Place rank or visibility movement for the keyword cluster",
                "agent output preserves evidence_trace and guardrails",
            ],
            "review_after_days": review_after_days,
            "success_threshold": "at least one accepted/completed signal and no unresolved guardrail feedback",
            "stop_condition": "hold or rewrite if rejected/failed feedback appears or human_review remains unresolved",
            "decision_state_at_creation": decision_packet.get("state"),
        }

    def _empty_feedback_snapshot(self) -> Dict[str, Any]:
        return {
            "total_events": 0,
            "counts": {},
            "latest_feedback_type": None,
            "latest_agent": None,
            "latest_note": None,
            "last_seen_at": None,
            "learning_status": "unseen",
        }

    def _attach_feedback_snapshots(self, cards: Sequence[Dict[str, Any]]) -> None:
        if not cards:
            return
        rows = self._feedback_rows([card.get("handoff_id", "") for card in cards])
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("handoff_id")), []).append(row)

        for card in cards:
            events = grouped.get(str(card.get("handoff_id")), [])
            if not events:
                card["feedback_snapshot"] = self._empty_feedback_snapshot()
                continue

            counts = Counter(str(event.get("feedback_type") or "unknown") for event in events)
            latest = events[0]
            card["feedback_snapshot"] = {
                "total_events": len(events),
                "counts": dict(counts),
                "latest_feedback_type": latest.get("feedback_type"),
                "latest_agent": latest.get("agent"),
                "latest_note": latest.get("note"),
                "last_seen_at": latest.get("created_at"),
                "learning_status": self._feedback_learning_status(counts),
            }
            if any(counts.get(key, 0) for key in ("needs_review", "rejected", "failed")):
                review = dict(card.get("human_review") or {})
                reasons = list(review.get("reasons") or [])
                for reason in ("feedback_review",):
                    if reason not in reasons:
                        reasons.append(reason)
                review.update({
                    "required": True,
                    "reasons": reasons,
                    "recommended_owner": "operator",
                })
                card["human_review"] = review
                self._apply_feedback_to_decision(card, counts)

    def _apply_feedback_to_decision(self, card: Dict[str, Any], counts: Counter) -> None:
        packet = dict(card.get("decision_packet") or {})
        reasons = list(packet.get("reason_codes") or [])
        if counts.get("rejected", 0) or counts.get("failed", 0):
            packet["state"] = "hold"
            packet["owner"] = "operator"
            packet["publish_policy"] = "operator_review_only"
            reasons.append("negative_feedback")
        elif counts.get("needs_review", 0):
            packet["state"] = "review"
            packet["owner"] = "operator"
            packet["publish_policy"] = "agent_can_draft_operator_must_review"
            reasons.append("feedback_review")
        packet["reason_codes"] = list(dict.fromkeys(reasons))
        card["decision_packet"] = packet
        plan = dict(card.get("measurement_plan") or {})
        plan["decision_state_after_feedback"] = packet.get("state")
        card["measurement_plan"] = plan

    def _feedback_rows(self, handoff_ids: Sequence[str]) -> List[Dict[str, Any]]:
        ids = [handoff_id for handoff_id in handoff_ids if handoff_id]
        if not ids:
            return []
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "pathfinder_insight_feedback"):
                return []
            placeholders = ", ".join("?" for _ in ids)
            cursor.execute(
                f"""
                SELECT handoff_id, keyword, agent, feedback_type, note, metadata_json, created_at
                FROM pathfinder_insight_feedback
                WHERE handoff_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                LIMIT 500
                """,
                ids,
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def _feedback_learning_status(self, counts: Counter) -> str:
        if not counts:
            return "unseen"
        negative = counts.get("rejected", 0) + counts.get("failed", 0)
        review = counts.get("needs_review", 0)
        positive = counts.get("accepted", 0) + counts.get("completed", 0) + counts.get("sent_to_agent", 0)
        if negative:
            return "intervention"
        if review:
            return "review"
        if positive:
            return "validated"
        return "observed"

    def _feedback_summary(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        total_events = 0
        counts: Counter = Counter()
        per_handoff: Dict[str, Dict[str, Any]] = {}
        for card in cards:
            snapshot = card.get("feedback_snapshot") or self._empty_feedback_snapshot()
            handoff_id = card.get("handoff_id")
            total_events += int(snapshot.get("total_events") or 0)
            counts.update(snapshot.get("counts") or {})
            if handoff_id:
                per_handoff[handoff_id] = {
                    "keyword": card.get("keyword"),
                    "learning_status": snapshot.get("learning_status"),
                    "counts": snapshot.get("counts") or {},
                    "last_seen_at": snapshot.get("last_seen_at"),
                }

        positive = counts.get("accepted", 0) + counts.get("completed", 0) + counts.get("sent_to_agent", 0)
        negative = counts.get("rejected", 0) + counts.get("failed", 0)
        actionable_rate = round(positive / total_events, 2) if total_events else None
        failure_rate = round(negative / total_events, 2) if total_events else None
        adjustments: List[str] = []
        if not total_events:
            adjustments.append("collect operator and agent feedback before treating insight quality as proven")
        if counts.get("needs_review", 0):
            adjustments.append("route needs_review handoffs to operator review before downstream publishing")
        if negative:
            adjustments.append("inspect rejected or failed handoffs and adjust scoring thresholds or guardrails")
        if counts.get("completed", 0):
            adjustments.append("promote completed handoffs as validated examples for future agent prompts")

        return {
            "total_events": total_events,
            "counts": dict(counts),
            "actionable_rate": actionable_rate,
            "failure_rate": failure_rate,
            "learning_status": self._feedback_learning_status(counts),
            "per_handoff": per_handoff,
            "recommended_adjustments": adjustments,
            "evaluation_contract": {
                "monitors": [
                    "accepted versus rejected handoffs",
                    "needs_review ratio",
                    "agent completion and failure outcomes",
                    "feedback attached to the same handoff_id as downstream drafts",
                ],
                "next_step": "use feedback_summary together with quality_gate before scaling automated execution",
            },
        }

    def _decision_overview(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        counts = Counter(
            (card.get("decision_packet") or {}).get("state", "unknown")
            for card in cards
        )
        go_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card.get("keyword"),
                "primary_metric": (card.get("measurement_plan") or {}).get("primary_metric"),
            }
            for card in cards
            if (card.get("decision_packet") or {}).get("state") == "go"
        ]
        review_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card.get("keyword"),
                "reasons": (card.get("decision_packet") or {}).get("reason_codes", []),
            }
            for card in cards
            if (card.get("decision_packet") or {}).get("state") in {"review", "hold"}
        ]
        return {
            "counts": dict(counts),
            "publishable_count": counts.get("go", 0),
            "operator_review_count": counts.get("review", 0) + counts.get("hold", 0),
            "go_cards": go_cards[:8],
            "review_cards": review_cards[:8],
            "measurement_contract": {
                "unit": "handoff_id",
                "must_track": [
                    "decision_packet.state",
                    "measurement_plan.primary_metric",
                    "feedback_snapshot.learning_status",
                    "human_review.required",
                    "data_quality.status",
                ],
                "cadence": "review after each content/ad execution and again at measurement_plan.review_after_days",
            },
        }

    def _why_it_matters(
        self,
        row: Dict[str, Any],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> List[str]:
        reasons: List[str] = []
        if _as_int(row.get("high_value_longtail")):
            reasons.append("고가치 롱테일로 판정됨")
        if _as_float(row.get("business_value_score")) >= 70:
            reasons.append("사업 가치 점수가 높음")
        if _as_float(row.get("longtail_score")) >= 70:
            reasons.append("구체적인 의사결정형 검색어")
        if _as_float(row.get("local_surface_score")) >= 70:
            reasons.append("로컬/플레이스 노출 가치가 큼")
        if _as_float(row.get("profile_action_signal")) >= 60:
            reasons.append("프로필 액션 전환 신호가 있음")
        if _as_float(row.get("review_surface_score")) >= 70:
            reasons.append("리뷰/평판 탐색 의도가 강함")
        if _as_float(row.get("availability_intent_score")) >= 70:
            reasons.append("예약/진료 가능 여부 확인 의도")
        if _as_float(row.get("payment_coverage_score")) >= 70:
            reasons.append("비용/보험/서류 확인 의도")
        if _as_float(row.get("access_convenience_score")) >= 70:
            reasons.append("주차/길찾기/접근성 같은 방문 편의 의도")
        if _as_float(row.get("community_signal")) >= 40:
            reasons.append("커뮤니티 수요 신호가 있음")
        if _as_float(row.get("conversion_signal")) >= 35:
            reasons.append("전화 전환 신호가 있음")
        if _as_float(row.get("mobile_share")) >= 0.65:
            reasons.append("모바일 로컬 검색 비중이 높음")
        if row.get("trend_status") == "rising":
            reasons.append("상승 추세")
        if len(source_signals) >= 2:
            reasons.append("다중 소스 검증")
        if not reasons and quality_flags:
            reasons.append("품질 플래그 기반 검토 필요")
        if not reasons:
            reasons.append("기본 Pathfinder 점수 기준 후보")
        return reasons[:8]

    def _risks(self, row: Dict[str, Any], quality_flags: Sequence[str]) -> List[str]:
        risks: List[str] = []
        if _as_float(row.get("medical_ad_risk_score")) >= 70:
            risks.append("의료광고 고위험 표현 금지")
        if _as_float(row.get("competitor_brand_risk_score")) >= 70:
            risks.append("경쟁사 브랜드 직접 비교 주의")
        if _as_float(row.get("reputation_risk_score")) >= 70:
            risks.append("평판 리스크 대응 문구 검토")
        if _as_float(row.get("content_actionability_score")) and _as_float(row.get("content_actionability_score")) < 45:
            risks.append("콘텐츠 실행 가능성 낮음")
        for flag in quality_flags:
            if any(token in flag for token in ("negative", "weak_service", "medical_ad", "competitor")):
                risks.append(f"품질 플래그: {flag}")
        return list(dict.fromkeys(risks))[:5]

    def _insight_score(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> float:
        base = max(
            _as_float(row.get("priority_v3")),
            _as_float(row.get("business_value_score")),
            _as_float(row.get("opportunity")),
            _as_float(row.get("opp_score")),
        )
        grade_bonus = {"S": 16.0, "A": 10.0, "B": 4.0}.get(str(row.get("grade") or "C"), 0.0)
        signal_bonus = min(18.0, len(reasons) * 2.5)
        risk_penalty = min(10.0, len(risks) * 2.0)
        return max(0.0, base + grade_bonus + signal_bonus - risk_penalty)

    def _agent_notes(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> Dict[str, str]:
        keyword = row.get("keyword", "")
        if _as_float(row.get("payment_coverage_score")) >= 70:
            blog_note = "비용/보험 적용 범위와 준비 서류를 정보형 FAQ로 풀 것"
            shorts_note = "보험/서류 체크리스트를 3컷 구조로 짧게 전달"
        elif _as_float(row.get("access_convenience_score")) >= 70:
            blog_note = "주차, 길찾기, 엘리베이터, 초진 동선을 방문 전 체크리스트로 구성"
            shorts_note = "입구, 주차, 접수 동선을 시각적으로 보여주는 방문 가이드"
        elif _as_float(row.get("availability_intent_score")) >= 70:
            blog_note = "당일/야간/주말 진료 가능 여부와 예약 방법을 명확히 설명"
            shorts_note = "대기 시간, 예약, 진료 가능 시간을 빠르게 확인시키는 훅"
        elif _as_float(row.get("review_surface_score")) >= 70:
            blog_note = "후기 자체보다 선택 기준과 확인 포인트를 중심으로 작성"
            shorts_note = "방문 전 확인할 3가지 기준을 카드형 쇼츠로 구성"
        elif _as_float(row.get("local_surface_score")) >= 70:
            blog_note = "지역명, 증상, 방문 행동을 자연스럽게 연결한 로컬 랜딩형 글"
            shorts_note = "지역 상황과 방문 맥락을 첫 3초 훅으로 제시"
        else:
            blog_note = "검색 의도, 증상 설명, 내원 전 확인사항을 균형 있게 구성"
            shorts_note = "문제 제기, 핵심 설명, 행동 유도 순서로 60초 이하 구성"

        guardrail = " / ".join(risks) if risks else "과장, 보장, 직접 비교 표현 금지"
        return {
            "blog_agent": f"{keyword}: {blog_note}. 가드레일: {guardrail}",
            "shorts_studio_agent": f"{keyword}: {shorts_note}. 가드레일: {guardrail}",
            "viral_hunter_agent": f"{keyword}: 커뮤니티 질문에 답할 때 광고성보다 확인 포인트 중심으로 대응",
            "ad_agent": f"{keyword}: 랜딩/광고 문구는 증상·방문 의도·확인 정보를 분리해 테스트",
        }

    def _keyword_actions(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> List[Dict[str, Any]]:
        keyword = row.get("keyword", "")
        return [
            {
                "owner": "blog_agent",
                "action": "create_blog_outline",
                "keyword": keyword,
                "priority": "high" if _as_float(row.get("business_value_score")) >= 70 else "medium",
                "angle": self._blog_angle(row),
                "must_include": reasons[:4],
                "avoid": risks or ["효과 보장", "과장된 비교", "후기 조작처럼 보이는 표현"],
            },
            {
                "owner": "shorts_studio_agent",
                "action": "create_short_script",
                "keyword": keyword,
                "priority": "high" if self._is_visual(row) else "medium",
                "angle": self._shorts_angle(row),
                "must_include": reasons[:3],
                "avoid": risks or ["자극적 치료 전후", "단정적 효과 표현"],
            },
        ]

    def _blog_angle(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "비용/보험/서류를 내원 전 확인하는 정보형 FAQ"
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "처음 방문하는 사용자를 위한 주차·길찾기·접근성 안내"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "예약 가능 시간과 진료 흐름을 설명하는 방문 준비 가이드"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "후기보다 중요한 선택 기준 정리"
        return "증상 원인, 치료 선택 기준, 내원 전 확인사항을 묶은 설명형 글"

    def _shorts_angle(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "주차부터 접수까지 15초 방문 동선"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "오늘 갈 수 있는지 확인하는 3단계"
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "보험/서류 질문에 답하는 체크리스트"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "방문 전 후기에서 확인할 3가지"
        return "검색자가 궁금해하는 핵심 질문 1개를 60초 안에 답변"

    def _is_visual(self, row: Dict[str, Any]) -> bool:
        return any(
            _as_float(row.get(col)) >= threshold
            for col, threshold in (
                ("access_convenience_score", 70),
                ("availability_intent_score", 70),
                ("local_surface_score", 70),
                ("review_surface_score", 70),
            )
        )

    def _brief_metrics(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        categories = Counter(card["category"] for card in cards)
        avg_confidence = (
            sum(float(card.get("confidence", 0)) for card in cards) / len(cards)
            if cards
            else 0.0
        )
        feedback_counts: Counter = Counter()
        for card in cards:
            feedback_counts.update((card.get("feedback_snapshot") or {}).get("counts") or {})
        decision_counts = Counter(
            (card.get("decision_packet") or {}).get("state", "unknown")
            for card in cards
        )
        place_snapshots = [card.get("place_rank") or {} for card in cards]
        place_tracked = [snap for snap in place_snapshots if snap.get("tracked")]
        visible_place = [
            snap for snap in place_tracked
            if (snap.get("current") or {}).get("status") == "found" and _as_int((snap.get("current") or {}).get("rank")) > 0
        ]
        place_ranks = [_as_int((snap.get("current") or {}).get("rank")) for snap in visible_place]
        return {
            "total_keywords": len(cards),
            "high_value_longtail_count": sum(1 for card in cards if card["signals"]["high_value_longtail"]),
            "access_intent_count": sum(1 for card in cards if card["metrics"].get("access_convenience_score", 0) >= 70),
            "payment_intent_count": sum(1 for card in cards if card["metrics"].get("payment_coverage_score", 0) >= 70),
            "availability_intent_count": sum(1 for card in cards if card["metrics"].get("availability_intent_score", 0) >= 70),
            "review_intent_count": sum(1 for card in cards if card["metrics"].get("review_surface_score", 0) >= 70),
            "risk_count": sum(1 for card in cards if card["risks"]),
            "avg_confidence": round(avg_confidence, 2),
            "low_confidence_count": sum(1 for card in cards if card.get("confidence", 0) < 0.58),
            "human_review_required_count": sum(1 for card in cards if card.get("human_review", {}).get("required")),
            "evidence_trace_count": sum(len(card.get("evidence_trace", [])) for card in cards),
            "feedback_event_count": sum(feedback_counts.values()),
            "feedback_counts": dict(feedback_counts),
            "decision_counts": dict(decision_counts),
            "measurement_plan_count": sum(1 for card in cards if card.get("measurement_plan")),
            "data_quality_thin_count": sum(1 for card in cards if (card.get("data_quality") or {}).get("status") == "thin"),
            "data_quality_caveat_count": sum(1 for card in cards if (card.get("data_quality") or {}).get("warnings")),
            "place_tracked_count": len(place_tracked),
            "place_visible_count": len(visible_place),
            "place_top3_count": sum(1 for rank in place_ranks if 0 < rank <= 3),
            "place_declining_count": sum(1 for snap in place_tracked if snap.get("trend") == "declined"),
            "place_improving_count": sum(1 for snap in place_tracked if snap.get("trend") == "improved"),
            "place_untracked_count": sum(1 for snap in place_snapshots if not snap.get("tracked")),
            "place_competitor_gap_count": sum(
                1
                for snap in place_tracked
                if snap.get("competitor_gap") is not None and snap.get("competitor_gap") > 0
            ),
            "avg_current_place_rank": round(sum(place_ranks) / len(place_ranks), 2) if place_ranks else None,
            "category_counts": dict(categories),
        }

    def _place_rows_from_snapshots(
        self,
        snapshots: Sequence[tuple[Optional[Dict[str, Any]], Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        rows = []
        for card, place in snapshots:
            current = place.get("current") or {}
            checked_at = place.get("latest_checked_at") or current.get("checked_at")
            if not place.get("tracked"):
                continue
            best_competitor = place.get("best_competitor") or {}
            rows.append({
                "handoff_id": (card or {}).get("handoff_id") if card else None,
                "keyword": (card or {}).get("keyword") or current.get("keyword"),
                "current_rank": current.get("rank"),
                "status": current.get("status"),
                "device_type": current.get("device_type"),
                "trend": place.get("trend"),
                "rank_delta": place.get("rank_delta"),
                "visibility_state": place.get("visibility_state"),
                "competitor_gap": place.get("competitor_gap"),
                "best_competitor": {
                    "target_name": best_competitor.get("target_name"),
                    "rank": best_competitor.get("rank"),
                    "device_type": best_competitor.get("device_type"),
                } if best_competitor else None,
                "checked_at": checked_at,
            })
        return rows

    def _recent_place_tracking_rows(self) -> List[Dict[str, Any]]:
        grouped = self._fetch_recent_place_rank_rows()
        own_terms = self._own_place_terms()
        snapshots: List[tuple[Optional[Dict[str, Any]], Dict[str, Any]]] = []
        for keyword, rows in grouped.items():
            snapshot = self._place_rank_snapshot_for_keyword(rows, own_terms)
            if snapshot.get("current"):
                snapshot["current"]["keyword"] = keyword
            snapshots.append(({"keyword": keyword}, snapshot))
        rows = self._place_rows_from_snapshots(snapshots)
        rows.sort(key=lambda item: str(item.get("checked_at") or ""), reverse=True)
        return rows[:8]

    def _place_tracking_summary(self, cards: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
        latest = None
        linked_rows = self._place_rows_from_snapshots([
            (card, card.get("place_rank") or {})
            for card in cards
        ])
        recent_rows = self._recent_place_tracking_rows() if len(linked_rows) < 3 else []
        rows = linked_rows if linked_rows else recent_rows

        for row in rows:
            checked_at = row.get("checked_at")
            if checked_at and (latest is None or str(checked_at) > str(latest)):
                latest = checked_at

        tracked_count = len(rows)
        visible_count = sum(1 for row in rows if row.get("status") == "found" and _as_int(row.get("current_rank")) > 0)
        top3_count = sum(1 for row in rows if row.get("status") == "found" and 0 < _as_int(row.get("current_rank")) <= 3)
        declining_count = sum(1 for row in rows if row.get("trend") == "declined")
        improving_count = sum(1 for row in rows if row.get("trend") == "improved")
        competitor_gap_count = sum(
            1 for row in rows if row.get("competitor_gap") is not None and row.get("competitor_gap") > 0
        )
        ranks = [_as_int(row.get("current_rank")) for row in rows if row.get("status") == "found" and _as_int(row.get("current_rank")) > 0]

        if not cards:
            headline = "플레이스 추적 인사이트가 아직 없습니다."
        elif not linked_rows and not recent_rows:
            headline = "상위 브리프 카드에 연결된 최신 플레이스 추적 결과가 없습니다."
        elif not linked_rows:
            headline = f"최근 플레이스 추적 {tracked_count}개를 별도 요약으로 표시합니다."
        elif declining_count:
            headline = f"플레이스 하락 키워드 {declining_count}개를 먼저 점검해야 합니다."
        elif competitor_gap_count:
            headline = f"경쟁사가 앞선 플레이스 키워드 {competitor_gap_count}개가 있습니다."
        elif top3_count:
            headline = f"Top3 플레이스 키워드 {top3_count}개는 방어 콘텐츠로 유지할 수 있습니다."
        else:
            headline = f"플레이스 추적 {tracked_count}개가 인사이트 카드에 연결되었습니다."

        return {
            "headline": headline,
            "source": "keyword_cards" if linked_rows else ("rank_history_recent" if recent_rows else "none"),
            "tracked_count": tracked_count,
            "visible_count": visible_count,
            "top3_count": top3_count,
            "declining_count": declining_count,
            "improving_count": improving_count,
            "competitor_gap_count": competitor_gap_count,
            "untracked_count": metrics.get("place_untracked_count", 0) if linked_rows else 0,
            "linked_card_count": len(linked_rows),
            "recent_fallback_count": len(recent_rows),
            "avg_current_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
            "latest_checked_at": latest,
            "cards": rows[:8],
            "linked_cards": linked_rows[:8],
            "recent_cards": recent_rows[:8],
        }

    def _place_rank_diagnostics(
        self,
        place_tracking: Dict[str, Any],
        actions: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tracked_count = _as_int(place_tracking.get("tracked_count"))
        visible_count = _as_int(place_tracking.get("visible_count"))
        top3_count = _as_int(place_tracking.get("top3_count"))
        declining_count = _as_int(place_tracking.get("declining_count"))
        competitor_gap_count = _as_int(place_tracking.get("competitor_gap_count"))
        avg_rank = place_tracking.get("avg_current_rank")

        if tracked_count <= 0:
            visibility_score = 0
            rank_quality_score = 0
            volatility_score = 0
            competitor_pressure_score = 0
        else:
            visible_rate = visible_count / tracked_count
            top3_rate = top3_count / tracked_count
            decline_rate = declining_count / tracked_count
            gap_rate = competitor_gap_count / tracked_count
            visibility_score = _clamp_int(visible_rate * 65 + top3_rate * 35)
            if avg_rank is None:
                rank_quality_score = 20 if visible_count else 0
            else:
                rank_quality_score = _clamp_int(110 - (_as_float(avg_rank) * 10))
            volatility_score = _clamp_int(100 - decline_rate * 100)
            competitor_pressure_score = _clamp_int(100 - gap_rate * 100)

        execution_readiness_score = _clamp_int(
            (20 if tracked_count else 0)
            + (20 if place_tracking.get("latest_checked_at") else 0)
            + (20 if place_tracking.get("source") != "none" else 0)
            + min(40, len(actions) * 8)
        )
        overall_score = _clamp_int(
            visibility_score * 0.30
            + rank_quality_score * 0.25
            + volatility_score * 0.20
            + competitor_pressure_score * 0.15
            + execution_readiness_score * 0.10
        )

        if tracked_count <= 0:
            interpretation = "측정 데이터가 부족해 먼저 추적 세팅이 필요합니다."
        elif visibility_score < 45:
            interpretation = "미노출 또는 낮은 노출 비중이 커서 정합성 복구가 우선입니다."
        elif competitor_pressure_score < 70:
            interpretation = "경쟁사 선점 압력이 있어 정보 충실도와 차별점 보강이 우선입니다."
        elif volatility_score < 80:
            interpretation = "최근 순위 하락 신호가 있어 변경 이력과 신선도 점검이 우선입니다."
        else:
            interpretation = "측정 가능한 상태이므로 Top3 방어와 콘텐츠 정렬 실험을 병행합니다."

        return {
            "overall_score": overall_score,
            "visibility_score": visibility_score,
            "rank_quality_score": rank_quality_score,
            "volatility_score": volatility_score,
            "competitor_pressure_score": competitor_pressure_score,
            "execution_readiness_score": execution_readiness_score,
            "interpretation": interpretation,
            "inputs": {
                "tracked_count": tracked_count,
                "visible_count": visible_count,
                "top3_count": top3_count,
                "declining_count": declining_count,
                "competitor_gap_count": competitor_gap_count,
                "avg_current_rank": avg_rank,
            },
        }

    def _place_rank_experiment_queue(self, actions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hypotheses = {
            "keyword_relevance": "업종, 대표키워드, 상세설명, 메뉴/서비스명이 검색 의도와 일치하면 미노출 상태가 개선된다.",
            "information_completeness": "사진, 서비스 설명, 예약/주문, 접근 정보가 실제 운영 상태와 맞으면 경쟁사 격차가 줄어든다.",
            "authentic_visit_feedback": "실방문 리뷰 안내와 답글 품질을 높이면 조작 없이 신뢰 신호가 안정화된다.",
            "freshness_and_trend": "최근 변경 이력과 신선도 항목을 정리하면 하락 추세가 멈춘다.",
            "local_content_alignment": "플레이스 정보와 블로그/FAQ/숏폼 메시지가 같은 지역 의도를 설명하면 Top3 진입 가능성이 높아진다.",
        }
        queue: List[Dict[str, Any]] = []
        for action in actions[:5]:
            action_id = str(action.get("action_id") or action.get("title") or "")
            seed = f"experiment:{action_id}:{action.get('keyword', '')}:{action.get('lever', '')}"
            queue.append({
                "experiment_id": "plx-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10],
                "keyword": action.get("keyword") or "공통 운영",
                "lever": action.get("lever"),
                "hypothesis": hypotheses.get(str(action.get("lever")), action.get("why", "")),
                "intervention": action.get("title"),
                "day_0_baseline": "rank_history의 현재 순위, 상태, 디바이스, 경쟁사 격차를 저장",
                "day_7_check": "상태가 악화되면 최근 수정 항목을 되돌리고 원인 후보를 분리",
                "day_14_decision": "성공 지표가 개선되면 유지, 변화가 없으면 다음 우선 액션으로 교체",
                "success_metric": action.get("measurement"),
                "guardrail": action.get("guardrail"),
                "tasks": list(action.get("tasks") or [])[:3],
            })
        return queue

    def _place_rank_automation_matrix(self) -> List[Dict[str, str]]:
        return [
            {
                "signal": "status in no_results/not_in_results/not_found",
                "system_action": "keyword_relevance recovery action",
                "owner": "pathfinder_operator",
                "cadence": "weekly",
            },
            {
                "signal": "trend == declined",
                "system_action": "freshness and recent-change audit",
                "owner": "pathfinder_operator",
                "cadence": "weekly",
            },
            {
                "signal": "competitor_gap > 0",
                "system_action": "profile completeness and differentiation audit",
                "owner": "pathfinder_operator",
                "cadence": "weekly",
            },
            {
                "signal": "current_rank between 1 and 3",
                "system_action": "Top3 defense routine",
                "owner": "pathfinder_operator",
                "cadence": "weekly",
            },
            {
                "signal": "rank > 3 and status == found",
                "system_action": "local content alignment experiment",
                "owner": "blog_agent",
                "cadence": "14 days",
            },
            {
                "signal": "review or reputation intent",
                "system_action": "authentic visitor review response loop",
                "owner": "pathfinder_operator",
                "cadence": "daily",
            },
            {
                "signal": "profile-linked landing/FAQ changed",
                "system_action": "Search Advisor diagnosis and IndexNow notification",
                "owner": "blog_agent",
                "cadence": "after each update",
            },
            {
                "signal": "operator asks for ranking shortcut",
                "system_action": "abuse-risk guardrail review before execution",
                "owner": "pathfinder_operator",
                "cadence": "always",
            },
        ]

    def _place_profile_audit_checklist(self, actions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        active_levers = {str(action.get("lever") or "") for action in actions}
        priority_order = {"high": 0, "medium": 1, "low": 2}
        rows: List[Dict[str, Any]] = []
        for field in self.PLACE_PROFILE_AUDIT_FIELDS:
            rank_signal = str(field.get("rank_signal") or "")
            urgent = rank_signal in active_levers or field.get("priority") == "high"
            rows.append({
                "field": field.get("field"),
                "rank_signal": rank_signal,
                "priority": field.get("priority"),
                "status": "urgent" if urgent else "monitor",
                "why": field.get("why"),
                "checks": list(field.get("checks") or []),
            })
        rows.sort(
            key=lambda item: (
                item.get("status") != "urgent",
                priority_order.get(str(item.get("priority")), 2),
                str(item.get("field") or ""),
            )
        )
        return rows

    def _normalize_place_keyword(self, keyword: Any) -> str:
        return re.sub(r"\s+", "", str(keyword or "")).lower()

    def _place_location_terms(self, keyword: str) -> List[str]:
        terms: List[str] = []
        for token in re.split(r"\s+", keyword.strip()):
            token = token.strip()
            if not token:
                continue
            if token in {"청주", "청주시"} or token.endswith(("동", "읍", "면", "구", "시", "군")):
                terms.append(token)
        compact = keyword.replace(" ", "")
        if not terms and "청주" in compact:
            terms.append("청주")
        if not terms:
            match = re.match(r"([가-힣]{2,}(?:동|읍|면|구|시|군))", compact)
            if match:
                terms.append(match.group(1))
        if not terms:
            match = re.search(r"([가-힣]{2,}(?:동|읍|면|구|시|군))", compact)
            if match:
                terms.append(match.group(1))
        return list(dict.fromkeys(terms))[:2]

    def _place_service_terms(self, card: Dict[str, Any], locations: Sequence[str]) -> List[str]:
        keyword = str(card.get("keyword") or "")
        compact_locations = {self._normalize_place_keyword(item) for item in locations}
        terms: List[str] = []
        for token in re.split(r"\s+", keyword.strip()):
            token = token.strip()
            if not token:
                continue
            token_norm = self._normalize_place_keyword(token)
            if token_norm in compact_locations:
                continue
            if any(location and location in token_norm for location in compact_locations):
                continue
            if token in self.PLACE_QUERY_STOPWORDS:
                continue
            if len(token) <= 1:
                continue
            terms.append(token)
        category = str(card.get("category") or "").strip()
        if category and category != "기타" and category not in terms:
            terms.append(category)
        if not any("한의원" in term for term in terms):
            terms.append("한의원")
        return list(dict.fromkeys(terms))[:4]

    def _place_core_service_phrase(self, services: Sequence[str], limit: int = 3) -> str:
        selected = list(dict.fromkeys(str(item).strip() for item in services if str(item).strip()))[:limit]
        for required in ("한의원", "의원", "병원"):
            if any(required in service for service in services) and not any(required in item for item in selected):
                if len(selected) >= limit:
                    selected[-1] = required
                else:
                    selected.append(required)
                break
        return " ".join(list(dict.fromkeys(selected))).strip()

    def _place_tracking_candidate_quality_issues(self, keyword: str) -> List[str]:
        tokens = [token for token in re.split(r"\s+", str(keyword or "").strip()) if token]
        norms = [self._normalize_place_keyword(token) for token in tokens]
        issues: List[str] = []
        if len(tokens) > 6:
            issues.append("too_many_terms")
        for idx, norm in enumerate(norms):
            if len(norm) < 3:
                continue
            if any(idx != other_idx and norm in other for other_idx, other in enumerate(norms)):
                issues.append("nested_duplicate_token")
                break
        return issues

    def _place_tracking_expansion_plan(
        self,
        cards: Sequence[Dict[str, Any]],
        place_tracking: Dict[str, Any],
        actions: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tracked_keywords = {
            str(row.get("keyword") or "")
            for row in (place_tracking.get("cards") or [])
            if row.get("keyword")
        }
        tracked_norm = {self._normalize_place_keyword(keyword) for keyword in tracked_keywords}
        candidate_rows: List[Dict[str, Any]] = []
        seen = set(tracked_norm)
        direct_tracked_cards = 0

        def add_candidate(
            *,
            keyword: str,
            source_keyword: str,
            reason: str,
            priority: str,
            pattern: str,
            source_handoff_id: Optional[str],
        ) -> None:
            clean = re.sub(r"\s+", " ", keyword).strip()
            norm = self._normalize_place_keyword(clean)
            quality_issues = self._place_tracking_candidate_quality_issues(clean)
            if not clean or norm in seen or quality_issues:
                return
            seen.add(norm)
            seed = f"{source_keyword}:{clean}:{pattern}"
            candidate_rows.append({
                "candidate_id": "pt-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10],
                "keyword": clean,
                "source_keyword": source_keyword,
                "source_handoff_id": source_handoff_id,
                "priority": priority,
                "pattern": pattern,
                "reason": reason,
                "device_targets": ["mobile", "pc"],
                "tracking_cadence": "weekly",
                "measurement": "rank_history.status, current_rank, trend, competitor_gap by device",
                "guardrail": "추적 후보는 순위 측정과 합법적 정보 보강에만 사용하고 키워드 스터핑에는 사용하지 않습니다.",
                "quality": {
                    "status": "clean",
                    "issues": [],
                },
            })

        for card in cards[:10]:
            source_keyword = str(card.get("keyword") or "").strip()
            if not source_keyword:
                continue
            source_norm = self._normalize_place_keyword(source_keyword)
            if source_norm in tracked_norm:
                direct_tracked_cards += 1
            locations = self._place_location_terms(source_keyword)
            services = self._place_service_terms(card, locations)
            location = locations[0] if locations else ""
            service = self._place_core_service_phrase(services, limit=3)
            priority = "high" if source_norm not in tracked_norm else "medium"

            add_candidate(
                keyword=source_keyword,
                source_keyword=source_keyword,
                source_handoff_id=card.get("handoff_id"),
                priority=priority,
                pattern="pathfinder_card_keyword",
                reason="Pathfinder 핵심 카드 키워드가 rank_history 직접 추적에 없으면 우선 측정해야 합니다.",
            )
            if location and service:
                add_candidate(
                    keyword=f"{location} {service}",
                    source_keyword=source_keyword,
                    source_handoff_id=card.get("handoff_id"),
                    priority=priority,
                    pattern="location_service_core",
                    reason="지역+서비스 핵심 조합은 플레이스 노출 기준선입니다.",
                )
                if "한의원" not in service:
                    add_candidate(
                        keyword=f"{location} {service} 한의원",
                        source_keyword=source_keyword,
                        source_handoff_id=card.get("handoff_id"),
                        priority=priority,
                        pattern="location_service_category",
                        reason="업종을 포함한 조합은 업체 정보 정합성 점검에 필요합니다.",
                    )
                for modifier in self.PLACE_QUERY_INTENT_MODIFIERS:
                    metric = str(modifier.get("metric") or "")
                    metric_value = _as_float((card.get("metrics") or {}).get(metric))
                    if metric_value >= 70 or metric == "business_value_score":
                        add_candidate(
                            keyword=f"{location} {service} {modifier['modifier']}",
                            source_keyword=source_keyword,
                            source_handoff_id=card.get("handoff_id"),
                            priority="high" if metric_value >= 70 else "medium",
                            pattern=f"intent_modifier:{modifier['modifier']}",
                            reason=str(modifier.get("reason") or ""),
                        )

        uncovered_count = max(0, len([card for card in cards if card.get("keyword")]) - direct_tracked_cards)
        coverage_rate = (
            round(direct_tracked_cards / len([card for card in cards if card.get("keyword")]), 2)
            if cards
            else 0.0
        )
        candidate_rows.sort(key=lambda item: (item["priority"] != "high", item["pattern"], item["keyword"]))
        return {
            "status": "ready" if candidate_rows else "covered",
            "tracked_keyword_count": len(tracked_keywords),
            "card_keyword_count": len([card for card in cards if card.get("keyword")]),
            "direct_tracked_card_count": direct_tracked_cards,
            "uncovered_card_count": uncovered_count,
            "coverage_rate": coverage_rate,
            "candidate_count": len(candidate_rows),
            "candidate_keywords": candidate_rows[:12],
            "tracked_keywords": sorted(tracked_keywords)[:20],
            "source": place_tracking.get("source") or "none",
            "next_step": (
                "상위 후보를 rank_history 모바일/PC 추적 큐에 추가한 뒤 14일 실험을 시작합니다."
                if candidate_rows
                else "현재 Pathfinder 카드 키워드는 직접 추적되고 있습니다."
            ),
            "guardrail": "후보 키워드는 측정 커버리지 확장용이며 스마트플레이스 설명이나 콘텐츠에 부자연스럽게 반복 삽입하지 않습니다.",
        }

    def _ensure_place_lift_context(
        self,
        cards: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not cards:
            return None
        if any(
            card.get("place_lift_actions")
            or card.get("place_tracking_candidates")
            or card.get("place_profile_audit")
            for card in cards
        ):
            return None
        metrics = self._brief_metrics(cards)
        place_tracking = self._place_tracking_summary(cards, metrics)
        place_rank_lift = self._place_rank_lift_plan(cards, metrics, place_tracking)
        self._attach_place_lift_context(cards, place_rank_lift)
        return place_rank_lift

    def _attach_place_lift_context(
        self,
        cards: Sequence[Dict[str, Any]],
        place_rank_lift: Optional[Dict[str, Any]],
    ) -> None:
        lift = place_rank_lift or {}
        actions = list(lift.get("handoff_actions") or lift.get("priority_actions") or [])
        experiments = list(lift.get("experiment_queue") or [])
        generic_actions = [action for action in actions if not action.get("keyword")]
        fallback_actions = generic_actions or actions[:2]
        profile_audit = list(lift.get("profile_audit_checklist") or [])[:5]
        tracking_candidates = list((lift.get("tracking_expansion") or {}).get("candidate_keywords") or [])

        for card in cards:
            keyword = str(card.get("keyword") or "")
            matched_actions = [
                action for action in actions
                if str(action.get("keyword") or "") == keyword
            ]
            matched_experiments = [
                experiment for experiment in experiments
                if str(experiment.get("keyword") or "") == keyword
            ]
            matched_candidates = [
                candidate for candidate in tracking_candidates
                if str(candidate.get("source_keyword") or "") == keyword
            ]
            card["place_lift_actions"] = (matched_actions or fallback_actions)[:4]
            card["place_lift_experiments"] = (matched_experiments or experiments[:2])[:2]
            card["place_tracking_candidates"] = (matched_candidates or tracking_candidates[:2])[:4]
            card["place_profile_audit"] = profile_audit

    def _place_representative_keyword_candidates(
        self,
        cards: Sequence[Dict[str, Any]],
        place_rank_lift: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        subjective_terms = {"후기", "추천", "잘하는곳", "잘하는", "비용", "가격", "가능", "근처", "주변"}
        candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add(keyword: str, *, source: str, reason: str, handoff_id: Optional[str] = None) -> None:
            clean = re.sub(r"\s+", " ", str(keyword or "")).strip()
            norm = self._normalize_place_keyword(clean)
            if not clean or norm in seen:
                return
            if any(term in clean for term in subjective_terms):
                return
            if len(clean.split()) > 5:
                return
            seen.add(norm)
            candidates.append({
                "keyword": clean,
                "source": source,
                "source_handoff_id": handoff_id,
                "reason": reason,
                "guardrail": "대표키워드는 최대 5개까지 실제 제공 서비스·메뉴명 중심으로만 검토하고 홍보성/주관적 표현은 제외합니다.",
            })

        tracking_candidates = (
            (place_rank_lift or {})
            .get("tracking_expansion", {})
            .get("candidate_keywords", [])
        )
        for item in tracking_candidates:
            pattern = str(item.get("pattern") or "")
            if pattern in {"location_service_core", "location_service_category"}:
                add(
                    str(item.get("keyword") or ""),
                    source="tracking_expansion",
                    handoff_id=item.get("source_handoff_id"),
                    reason="Pathfinder 상위 의도를 지역+실제 서비스명 형태로 정제한 대표키워드 후보",
                )

        for card in cards[:8]:
            locations = self._place_location_terms(str(card.get("keyword") or ""))
            services = self._place_service_terms(card, locations)
            location = locations[0] if locations else ""
            if services:
                keyword = f"{location} {self._place_core_service_phrase(services, limit=3)}".strip()
                add(
                    keyword,
                    source="keyword_card",
                    handoff_id=card.get("handoff_id"),
                    reason="키워드 카드의 로컬·서비스 의도를 스마트플레이스 대표키워드 검토 단위로 축약",
                )
        return candidates[:5]

    def _place_value_content_briefs(
        self,
        cards: Sequence[Dict[str, Any]],
        representative_keywords: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rep_by_handoff = {
            item.get("source_handoff_id"): item.get("keyword")
            for item in representative_keywords
            if item.get("source_handoff_id")
        }
        briefs: List[Dict[str, Any]] = []
        for card in cards[:6]:
            metrics = card.get("metrics") or {}
            keyword = str(card.get("keyword") or "")
            rep_keyword = rep_by_handoff.get(card.get("handoff_id"))
            if not rep_keyword:
                locations = self._place_location_terms(keyword)
                services = self._place_service_terms(card, locations)
                rep_keyword = f"{locations[0] if locations else ''} {self._place_core_service_phrase(services, limit=3)}".strip()
            faq_topics: List[str] = []
            photo_prompts: List[str] = ["외관/입구", "진료실 또는 서비스 공간", "최근 운영 상태를 보여주는 사진"]
            smartplace_field = "상세설명/대표키워드"
            if _as_float(metrics.get("payment_coverage_score")) >= 70:
                faq_topics.append("비용·보험·서류 범위를 확인 가능한 수준으로 설명")
                smartplace_field = "가격표/상세설명/FAQ"
            if _as_float(metrics.get("access_convenience_score")) >= 70:
                faq_topics.append("주차·엘리베이터·찾아오는 길·접근성 안내")
                photo_prompts.append("주차/입구/엘리베이터/휠체어 접근 가능 여부")
                smartplace_field = "부가정보/찾아오는 길/사진"
            if _as_float(metrics.get("availability_intent_score")) >= 70:
                faq_topics.append("예약 가능 시간과 문의 흐름")
                smartplace_field = "예약/영업시간/톡톡"
            if _as_float(metrics.get("review_surface_score")) >= 70:
                faq_topics.append("실제 방문자가 자주 묻는 선택 기준")
            if not faq_topics:
                faq_topics.append("대표 서비스가 어떤 방문 상황에 맞는지 설명")

            briefs.append({
                "handoff_id": card.get("handoff_id"),
                "source_keyword": keyword,
                "representative_keyword_candidate": rep_keyword,
                "smartplace_field": smartplace_field,
                "profile_message": f"{rep_keyword or keyword} 의도를 업체정보·상세설명·FAQ에 자연스럽게 연결",
                "faq_topics": faq_topics[:4],
                "photo_prompts": list(dict.fromkeys(photo_prompts))[:5],
                "review_response_focus": "방문 경험을 조작하지 않고 실제 문의·불편·칭찬 포인트에 답글로 응답",
                "do_not": [
                    "대표키워드 5개 제한을 넘기지 않음",
                    "업체명·주소·설명에 키워드를 반복 삽입하지 않음",
                    "리뷰 별점·문구·수정·삭제를 강요하지 않음",
                ],
                "measurement": "SmartPlace profile update date, rank_history trend, content/review response coverage",
            })
        return briefs

    def _place_value_loop(
        self,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        place_tracking: Optional[Dict[str, Any]],
        place_rank_lift: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rep_keywords = self._place_representative_keyword_candidates(cards, place_rank_lift)
        content_briefs = self._place_value_content_briefs(cards, rep_keywords)
        has_access = metrics.get("access_intent_count", 0) > 0
        has_payment = metrics.get("payment_intent_count", 0) > 0
        has_availability = metrics.get("availability_intent_count", 0) > 0
        has_review = metrics.get("review_intent_count", 0) > 0
        tracking = place_tracking or {}
        lift = place_rank_lift or {}
        ai_readiness_score = _clamp_int(
            min(30, len(rep_keywords) * 6)
            + min(25, len(content_briefs) * 4)
            + (15 if has_review else 0)
            + (10 if has_access else 0)
            + (10 if has_availability else 0)
            + (10 if tracking.get("tracked_count") else 0)
        )
        smartplace_updates = [
            {
                "field": "대표키워드",
                "priority": "high",
                "action": "Pathfinder 상위 의도에서 실제 서비스명 후보 최대 5개를 검토",
                "payload": [item.get("keyword") for item in rep_keywords],
                "guardrail": "대표키워드는 실제 제공 서비스·메뉴명 중심이며 홍보성/주관적 표현은 제외",
                "measurement": "대표키워드 변경 후 14일간 rank_history와 SmartPlace 검색어 통계를 비교",
            },
            {
                "field": "상세설명/FAQ",
                "priority": "high" if has_payment or has_access else "medium",
                "action": "비용·보험·주차·예약·방문 준비 질문을 상세설명과 FAQ 후보로 전환",
                "payload": list(dict.fromkeys(topic for brief in content_briefs for topic in brief.get("faq_topics", [])))[:8],
                "guardrail": "의료 효과 보장, 비교 우위 단정, 키워드 반복 삽입 금지",
                "measurement": "FAQ 반영 키워드의 노출 상태와 상담 문의 전환 메모",
            },
            {
                "field": "사진/이미지",
                "priority": "high",
                "action": "업주 등록 사진을 최신 상태로 유지하고 의도별 확인 사진을 보강",
                "payload": list(dict.fromkeys(prompt for brief in content_briefs for prompt in brief.get("photo_prompts", [])))[:8],
                "guardrail": "실제 공간·시설·서비스만 촬영하고 리뷰/이미지 조작 금지",
                "measurement": "사진 업데이트일과 AI 롱테일/검색결과 이미지 노출 변화",
            },
            {
                "field": "예약/톡톡/스마트콜/부가정보",
                "priority": "high" if has_availability or has_access else "medium",
                "action": "예약 가능성, 문의 채널, 주차·장애인 시설·결제수단·홈페이지/SNS 정보를 점검",
                "payload": ["예약/문의 버튼", "영업시간/휴무", "주차/장애인 시설", "결제수단", "홈페이지/SNS"],
                "guardrail": "실제 운영하지 않는 예약·쿠폰·시설을 표시하지 않음",
                "measurement": "SmartPlace 통계의 전화/예약/톡톡/방문 행동 변화",
            },
            {
                "field": "리뷰 응답/AI 브리핑",
                "priority": "high" if has_review else "medium",
                "action": "실제 방문 리뷰에 답글하고 반복 질문을 FAQ와 상세설명 개선으로 환류",
                "payload": [brief.get("review_response_focus") for brief in content_briefs[:4]],
                "guardrail": "리뷰 작성 보상, 별점/문구 강요, 개인정보 추정·공개 금지",
                "measurement": "리뷰 답글 커버리지와 AI 브리핑/리뷰 스니펫의 부정확 표현 점검",
            },
        ]
        import_signals = [
            {
                "source": "SmartPlace 인기 검색어/통계",
                "pathfinder_update": "신규 keyword_insights 후보와 rank_history 추적 후보로 편입",
                "cadence": "weekly",
                "owner": "pathfinder_operator",
            },
            {
                "source": "방문자 리뷰 키워드·AI 브리핑 문구",
                "pathfinder_update": "review_surface_score와 FAQ/콘텐츠 각도 보정",
                "cadence": "weekly",
                "owner": "viral_hunter_agent",
            },
            {
                "source": "사진·리뷰 이미지 노출 상태",
                "pathfinder_update": "local_content_alignment와 이미지 보강 작업 생성",
                "cadence": "weekly",
                "owner": "shorts_studio_agent",
            },
            {
                "source": "예약/주문/톡톡/스마트콜 행동 통계",
                "pathfinder_update": "availability_intent_score와 conversion_signal 보정",
                "cadence": "weekly",
                "owner": "ad_agent",
            },
            {
                "source": "대표키워드·업체정보 변경 이력",
                "pathfinder_update": "변경 후 14일 실험 큐와 rank_history 재측정",
                "cadence": "after each update",
                "owner": "pathfinder_operator",
            },
        ]
        experiments = [
            {
                "experiment_id": "pv-" + hashlib.sha1(str(item.get("keyword")).encode("utf-8")).hexdigest()[:10],
                "keyword": item.get("keyword"),
                "hypothesis": "대표키워드/상세설명/FAQ/사진을 같은 의도로 정렬하면 AI 롱테일·지도 검색 적합성이 개선된다.",
                "day_0": "현재 rank_history, SmartPlace 통계, 업데이트 전 프로필 상태 저장",
                "day_14": "순위, 노출 상태, 검색어/전화/예약/톡톡 변화 비교",
                "guardrail": item.get("guardrail"),
            }
            for item in rep_keywords[:5]
        ]
        source_urls = {
            "https://help.naver.com/service/30026/contents/20379?lang=ko",
            "https://help.naver.com/service/30026/contents/20429?lang=ko",
            "https://help.naver.com/service/30026/contents/25167?lang=ko&osType=COMMONOS",
            "https://help.naver.com/service/30026/contents/24632?osType=COMMONOS",
            "https://help.naver.com/service/30026/contents/20402?lang=ko",
            "https://smartplace.naver.com/notices/1018",
        }
        return {
            "status": "ready" if cards else "empty",
            "headline": "Pathfinder 인사이트를 스마트플레이스 정보·사진·FAQ·리뷰 응답으로 환류하고, 플레이스 통계를 다시 Pathfinder 우선순위에 반영합니다.",
            "pathfinder_to_place": {
                "representative_keyword_candidates": rep_keywords,
                "smartplace_updates": smartplace_updates,
                "content_briefs": content_briefs,
                "ai_longtail_readiness": {
                    "score": ai_readiness_score,
                    "basis": "업체정보, 블로그/방문자 리뷰, 이미지 의미 매칭을 준비하는 운영 점수",
                    "next_step": "상위 대표키워드 후보와 FAQ/사진 보강안을 먼저 검토",
                },
            },
            "place_to_pathfinder": {
                "import_signals": import_signals,
                "reverse_handoffs": [
                    "SmartPlace 인기 검색어를 Pathfinder 후보 수집에 투입",
                    "리뷰 키워드와 AI 브리핑 문구를 FAQ/블로그/쇼츠 각도에 반영",
                    "예약/전화/톡톡 행동 변화를 conversion_signal과 실험 성공 지표로 반영",
                ],
                "measurement_contract": {
                    "unit": "representative_keyword_candidate + handoff_id",
                    "review_after_days": 14,
                    "primary_metrics": [
                        "rank_history.current_rank",
                        "SmartPlace popular search terms",
                        "SmartPlace call/reservation/talktalk actions",
                    ],
                },
            },
            "closed_loop_experiments": experiments,
            "source_refs": [ref for ref in self.PLACE_RANK_SOURCE_REFS if ref.get("url") in source_urls],
            "guardrails": list(dict.fromkeys((lift.get("prohibited_tactics") or self.PLACE_RANK_PROHIBITED_TACTICS)))[:8],
        }

    def _attach_place_value_context(
        self,
        cards: Sequence[Dict[str, Any]],
        place_value_loop: Optional[Dict[str, Any]],
    ) -> None:
        briefs = list(((place_value_loop or {}).get("pathfinder_to_place") or {}).get("content_briefs") or [])
        by_handoff = {brief.get("handoff_id"): brief for brief in briefs if brief.get("handoff_id")}
        fallback = briefs[0] if briefs else {}
        for card in cards:
            card["place_value_brief"] = by_handoff.get(card.get("handoff_id"), fallback)

    def _ensure_place_value_context(
        self,
        cards: Sequence[Dict[str, Any]],
        *,
        place_rank_lift: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not cards:
            return None
        if any(card.get("place_value_brief") for card in cards):
            return None
        metrics = self._brief_metrics(cards)
        place_tracking = self._place_tracking_summary(cards, metrics)
        lift = place_rank_lift or self._place_rank_lift_plan(cards, metrics, place_tracking)
        if lift and not any(card.get("place_lift_actions") for card in cards):
            self._attach_place_lift_context(cards, lift)
        loop = self._place_value_loop(cards, metrics, place_tracking, lift)
        self._attach_place_value_context(cards, loop)
        return loop

    def _place_rank_lift_plan(
        self,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        place_tracking: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        place = place_tracking or {}
        rows = list(place.get("cards") or [])
        basis_by_lever = {
            item["lever"]: item
            for item in self.PLACE_RANK_RESEARCH_BASIS
        }
        actions: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_action(
            *,
            lever: str,
            title: str,
            keyword: str = "",
            priority: str = "medium",
            why: str,
            tasks: Sequence[str],
            measurement: str,
            owner: str = "pathfinder_operator",
            cadence: str = "weekly",
        ) -> None:
            key = (lever, keyword)
            if key in seen:
                return
            seen.add(key)
            seed = f"{lever}:{keyword}:{title}:{measurement}"
            actions.append({
                "action_id": "pl-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10],
                "lever": lever,
                "keyword": keyword,
                "priority": priority,
                "title": title,
                "why": why,
                "tasks": list(tasks),
                "measurement": measurement,
                "owner": owner,
                "cadence": cadence,
                "research_basis": basis_by_lever.get(lever, {}),
                "guardrail": "허위 클릭, 허위 예약, 허위 리뷰, 별점/문구 통제 없이 실제 업체 정보와 방문 경험만 개선합니다.",
            })

        for row in rows:
            keyword = str(row.get("keyword") or "")
            status = str(row.get("status") or "unknown")
            rank = _as_int(row.get("current_rank"))
            trend = str(row.get("trend") or "unknown")
            competitor_gap = row.get("competitor_gap")
            gap = _as_int(competitor_gap) if competitor_gap is not None else 0
            competitor = row.get("best_competitor") or {}

            if status != "found" or rank <= 0:
                add_action(
                    lever="keyword_relevance",
                    keyword=keyword,
                    priority="high",
                    title="미노출 키워드 정합성 복구",
                    why=f"{keyword or 'tracked keyword'}에서 현재 상태가 {status}입니다.",
                    tasks=[
                        "대표키워드 5개가 실제 메뉴명, 서비스명, 상품명과 일치하는지 점검",
                        "업종, 상세설명, 찾아오는 길, 주소, 메뉴/서비스명이 같은 의도를 가리키도록 정리",
                        "홍보성/주관적 표현과 무관한 지역명 삽입을 제거",
                        "수정 후 모바일/PC rank_history를 같은 키워드로 재측정",
                    ],
                    measurement="status becomes found and current_rank enters top10 within the tracked device",
                )
                continue

            if trend == "declined":
                add_action(
                    lever="freshness_and_trend",
                    keyword=keyword,
                    priority="high",
                    title="순위 하락 원인 점검",
                    why=f"{keyword}의 최신 순위가 {rank}위이고 이전 대비 하락했습니다.",
                    tasks=[
                        "최근 업체명, 업종, 대표키워드, 전화번호, 주소, 영업시간 변경 이력을 확인",
                        "사진, 메뉴/서비스, 공지, 예약 가능 정보가 실제 운영 상태와 맞는지 갱신",
                        "최근 리뷰 답글과 질문 답변 누락분을 정리",
                        "하락 키워드와 같은 의도의 블로그/FAQ 콘텐츠를 보강",
                    ],
                    measurement="rank_delta returns to zero or positive on the next two scans",
                )

            if gap > 0:
                competitor_name = competitor.get("target_name") or "선행 경쟁사"
                competitor_rank = competitor.get("rank") or "-"
                add_action(
                    lever="information_completeness",
                    keyword=keyword,
                    priority="high",
                    title="경쟁사 선점 격차 축소",
                    why=f"{keyword}에서 {competitor_name} {competitor_rank}위가 우리보다 {gap}계단 앞서 있습니다.",
                    tasks=[
                        "상위 경쟁사 대비 사진 수, 최신 사진, 메뉴/서비스 설명, 주차/시설, 예약/주문 노출 항목을 비교",
                        "부족한 항목은 실제 운영 정보로 보완하고 과장 문구를 제거",
                        "방문자가 고르는 기준을 FAQ와 블로그 콘텐츠로 설명",
                        "경쟁사 비방 없이 우리 서비스의 확인 가능한 차별점만 기록",
                    ],
                    measurement="competitor_gap decreases or reaches zero for the tracked keyword",
                )

            if 0 < rank <= 3:
                add_action(
                    lever="freshness_and_trend",
                    keyword=keyword,
                    priority="medium",
                    title="Top3 방어 루틴",
                    why=f"{keyword}는 현재 {rank}위라 방어와 변동 감시가 우선입니다.",
                    tasks=[
                        "영업시간, 휴무, 예약, 공지, 사진을 주 1회 실제 상태와 대조",
                        "실방문 리뷰에는 개인정보 노출 없이 사업주 답글을 남김",
                        "Top3 키워드와 같은 의도의 FAQ/숏폼을 유지",
                    ],
                    measurement="current_rank stays within top3 for two consecutive weekly scans",
                )
            elif rank > 3:
                add_action(
                    lever="local_content_alignment",
                    keyword=keyword,
                    priority="medium",
                    title="Top3 진입 콘텐츠 정렬",
                    why=f"{keyword}는 노출 중이지만 현재 {rank}위로 상위권 진입 여지가 있습니다.",
                    tasks=[
                        "키워드 의도에 맞는 블로그 개요, FAQ, 숏폼 훅을 같은 메시지로 정렬",
                        "상세설명과 콘텐츠의 서비스명, 방문 준비 정보, 비용/예약 안내가 충돌하지 않게 수정",
                        "콘텐츠 발행 후 rank_history와 사용자 반응을 함께 확인",
                    ],
                    measurement="current_rank improves by at least one position or reaches top3",
                    owner="blog_agent",
                )

        if not rows:
            add_action(
                lever="freshness_and_trend",
                priority="high",
                title="플레이스 순위 추적 세팅",
                why="현재 화면에 연결된 플레이스 추적 행이 부족해 개선 효과를 측정하기 어렵습니다.",
                tasks=[
                    "핵심 지역+서비스 키워드를 rank_history 추적 대상으로 추가",
                    "모바일과 PC를 분리해 같은 시간대에 반복 측정",
                    "no_results, not_in_results, found 상태를 화면 리프트 플랜에 연결",
                ],
                measurement="tracked_count is greater than zero and latest_checked_at is populated",
            )

        add_action(
            lever="authentic_visit_feedback",
            priority="high" if rows else "medium",
            title="실방문 리뷰 신뢰 루프",
            why="리뷰는 방문 경험의 신뢰 신호가 될 수 있지만 조작은 업체 단위 페널티 위험이 큽니다.",
            tasks=[
                "실제 방문 고객에게만 자율 리뷰 작성을 안내",
                "별점, 문구, 긍정 표현, 수정/삭제를 요구하지 않음",
                "리뷰 답글에서 개인정보, 압박, 비방 표현을 배제",
                "반복 질문은 FAQ와 상세설명 개선 항목으로 전환",
            ],
            measurement="real visitor review response coverage and review-risk incidents remain within guardrail",
            owner="pathfinder_operator",
            cadence="daily",
        )

        add_action(
            lever="information_completeness",
            priority="medium",
            title="스마트플레이스 정보 충실도 보강",
            why="공식 기준상 정확하고 풍부한 업체 정보가 검색어 매칭과 방문 경험의 기반입니다.",
            tasks=[
                "영업시간, 휴무일, 전화번호, 주소, 지도 핀, 찾아오는 길을 실제 상태와 대조",
                "사진, 메뉴/서비스, 주차/시설, 결제수단, 홈페이지/SNS, 예약/주문 항목을 보완",
                "업체명과 대표키워드에 확인되지 않는 지역명, 미사여구, 홍보성 문구를 넣지 않음",
            ],
            measurement="profile completeness checklist has no unresolved required item before the next rank scan",
        )

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        actions.sort(
            key=lambda item: (
                0 if item.get("keyword") else 1,
                priority_order.get(str(item.get("priority")), 2),
                str(item.get("keyword") or ""),
                str(item.get("lever") or ""),
            )
        )

        headline = "플레이스 순위 리프트 플랜을 실행 가능한 액션으로 준비했습니다."
        if not rows:
            headline = "플레이스 추적 데이터가 부족해 측정 세팅과 기본 최적화부터 진행합니다."
        elif place.get("declining_count"):
            headline = f"하락 키워드 {place.get('declining_count')}개를 우선 복구 대상으로 분리했습니다."
        elif place.get("competitor_gap_count"):
            headline = f"경쟁사가 앞선 키워드 {place.get('competitor_gap_count')}개를 격차 축소 대상으로 분리했습니다."
        elif place.get("top3_count"):
            headline = f"Top3 키워드 {place.get('top3_count')}개는 방어 루틴으로 관리합니다."

        diagnostic_scores = self._place_rank_diagnostics(place, actions)
        experiment_queue = self._place_rank_experiment_queue(actions)
        profile_audit_checklist = self._place_profile_audit_checklist(actions)
        tracking_expansion = self._place_tracking_expansion_plan(cards, place, actions)
        handoff_actions = list(actions[:8])
        for action in [item for item in actions if not item.get("keyword")][:2]:
            if action not in handoff_actions:
                handoff_actions.append(action)

        return {
            "status": "ready" if actions else "empty",
            "source": place.get("source") or "none",
            "headline": headline,
            "tracked_count": place.get("tracked_count", metrics.get("place_tracked_count", 0)),
            "priority_action_count": len(actions),
            "source_refs": self.PLACE_RANK_SOURCE_REFS,
            "research_basis": self.PLACE_RANK_RESEARCH_BASIS,
            "prohibited_tactics": self.PLACE_RANK_PROHIBITED_TACTICS,
            "diagnostic_scores": diagnostic_scores,
            "priority_actions": actions[:8],
            "handoff_actions": handoff_actions[:10],
            "experiment_queue": experiment_queue,
            "profile_audit_checklist": profile_audit_checklist,
            "tracking_expansion": tracking_expansion,
            "automation_matrix": self._place_rank_automation_matrix(),
            "weekly_checklist": [
                "rank_history에서 미노출, 하락, 경쟁사 선점 키워드를 먼저 확인",
                "tracking_expansion의 상위 후보를 모바일/PC 추적 큐에 추가",
                "대표키워드 5개와 실제 서비스/메뉴/상품명의 정합성 점검",
                "영업시간, 휴무, 예약, 사진, 주차/시설, 찾아오는 길 최신화",
                "실방문 리뷰 답글과 반복 질문을 FAQ/상세설명 개선으로 전환",
                "발행 콘텐츠가 실제 제공 서비스와 같은 지역 의도를 설명하는지 검토",
            ],
            "measurement_contract": {
                "primary_metric": "rank_history.current_rank by keyword and device",
                "secondary_metrics": [
                    "place_tracking.visible_count",
                    "place_tracking.top3_count",
                    "place_tracking.competitor_gap_count",
                    "place_tracking.declining_count",
                ],
                "review_after_days": 14,
                "guardrail_metric": "zero fake click, fake booking, fake receipt, forced review, or competitor attack incidents",
            },
        }

    def _build_summary(
        self,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        place_tracking: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        top = cards[0] if cards else None
        if not top:
            headline = "Pathfinder 인사이트가 아직 없습니다"
            next_best_action = "Legion 모드를 실행해 최신 검증 키워드를 확보하세요."
        else:
            headline = f"가장 먼저 실행할 키워드는 '{top['keyword']}'입니다"
            next_best_action = top["recommended_actions"][0]["angle"]
            place = top.get("place_rank") or {}
            current = place.get("current") or {}
            if place.get("tracked") and current.get("status") == "found" and current.get("rank"):
                next_best_action = (
                    f"{next_best_action} 현재 플레이스 {current.get('rank')}위"
                    f"({current.get('device_type', 'unknown')}) 맥락을 함께 반영하세요."
                )
            elif place_tracking and place_tracking.get("source") == "rank_history_recent":
                next_best_action = (
                    f"{next_best_action} 최신 플레이스 추적 요약도 함께 확인하세요: "
                    f"{place_tracking.get('headline')}"
                )
        return {
            "headline": headline,
            "next_best_action": next_best_action,
            "agent_ready": bool(cards),
            "handoff_targets": ["blog_agent", "shorts_studio_agent", "viral_hunter_agent", "ad_agent"],
            "confidence": {
                "average": metrics.get("avg_confidence", 0.0),
                "band": self._confidence_band(float(metrics.get("avg_confidence", 0.0))),
                "human_review_required": metrics.get("human_review_required_count", 0),
            },
            "decision_counts": metrics.get("decision_counts", {}),
            "coverage": metrics,
        }

    def _build_top_insights(
        self,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        place_tracking: Optional[Dict[str, Any]] = None,
        place_rank_lift: Optional[Dict[str, Any]] = None,
        place_value_loop: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        if not cards:
            return ["최신 Pathfinder Legion 결과가 없어 인사이트 브리프를 만들 수 없습니다."]
        insights = [
            f"상위 {len(cards)}개 후보 중 고가치 롱테일은 {metrics['high_value_longtail_count']}개입니다.",
        ]
        if metrics["access_intent_count"]:
            insights.append(f"방문 편의/접근성 의도가 {metrics['access_intent_count']}개 있어 쇼츠와 플레이스형 콘텐츠에 적합합니다.")
        if metrics["payment_intent_count"]:
            insights.append(f"비용/보험 확인 의도가 {metrics['payment_intent_count']}개 있어 FAQ형 블로그로 전환 설명을 강화해야 합니다.")
        if metrics["availability_intent_count"]:
            insights.append(f"예약/시간 민감 의도가 {metrics['availability_intent_count']}개 있어 즉시성 있는 CTA가 필요합니다.")
        if metrics["review_intent_count"]:
            insights.append(f"리뷰/평판 탐색 의도가 {metrics['review_intent_count']}개 있어 후기보다 선택 기준 중심의 메시지가 안전합니다.")
        place = place_tracking or {}
        if place.get("tracked_count"):
            insights.append(
                f"플레이스 추적 결과 {place['tracked_count']}개가 화면 요약에 포함되어 현재 순위와 실행 우선순위를 함께 봅니다."
            )
        if place.get("declining_count"):
            insights.append(
                f"플레이스 하락 키워드 {place['declining_count']}개는 원인 점검과 방어 콘텐츠가 우선입니다."
            )
        if place.get("competitor_gap_count"):
            insights.append(
                f"경쟁사가 앞선 플레이스 키워드 {place['competitor_gap_count']}개는 경쟁사 대비 메시지 차별화가 필요합니다."
            )
        lift = place_rank_lift or {}
        if lift.get("priority_actions"):
            first = lift["priority_actions"][0]
            insights.append(
                f"플레이스 리프트 우선 액션은 {first.get('title')}이며 측정 기준은 {first.get('measurement')}입니다."
            )
        value_loop = place_value_loop or {}
        representative_keywords = (
            (value_loop.get("pathfinder_to_place") or {})
            .get("representative_keyword_candidates", [])
        )
        if representative_keywords:
            insights.append(
                f"Pathfinder 인사이트에서 스마트플레이스 대표키워드 후보 {len(representative_keywords)}개를 추렸고, 최대 5개 제한과 키워드 스터핑 가드레일로 검토합니다."
            )
        readiness = (
            (value_loop.get("pathfinder_to_place") or {})
            .get("ai_longtail_readiness", {})
            .get("score")
        )
        if readiness is not None:
            insights.append(
                f"플레이스 AI 롱테일 준비도는 {readiness}점으로, 업체정보·사진·FAQ·리뷰 응답을 같은 의도로 정렬해야 합니다."
            )
        if metrics["risk_count"]:
            insights.append(f"{metrics['risk_count']}개 후보는 의료광고/브랜드/평판 가드레일 검토 후 실행해야 합니다.")
        if metrics.get("human_review_required_count"):
            insights.append(
                f"{metrics['human_review_required_count']}개 후보는 신뢰도·근거·가드레일 기준상 사람 검토가 먼저 필요합니다."
            )
        if metrics.get("feedback_event_count"):
            insights.append(
                f"기존 피드백 {metrics['feedback_event_count']}건이 반영되어 승인/검토/실패 이력을 함께 봅니다."
            )
        decision_counts = metrics.get("decision_counts") or {}
        if decision_counts:
            insights.append(
                f"실행 상태는 go {decision_counts.get('go', 0)}개, review {decision_counts.get('review', 0)}개, hold {decision_counts.get('hold', 0)}개입니다."
            )
        top_categories = ", ".join(name for name, _ in Counter(metrics["category_counts"]).most_common(3))
        if top_categories:
            insights.append(f"우선 카테고리는 {top_categories}입니다.")
        return insights[:7]

    def _build_provenance(
        self,
        cards: Sequence[Dict[str, Any]],
        *,
        latest_verified_only: bool,
        business_core_only: bool,
    ) -> Dict[str, Any]:
        run_ids = sorted({
            card.get("provenance", {}).get("last_scan_run_id")
            for card in cards
            if card.get("provenance", {}).get("last_scan_run_id")
        })
        sources = sorted({
            card.get("provenance", {}).get("source") or "pathfinder"
            for card in cards
        })
        return {
            "model": "w3c-prov-lite",
            "source_table": "keyword_insights",
            "database": Path(self.db_path).name,
            "latest_verified_only": latest_verified_only,
            "business_core_only": business_core_only,
            "last_scan_run_ids": run_ids,
            "source_labels": sources,
            "cards": [
                {
                    "handoff_id": card.get("handoff_id"),
                    "keyword": card.get("keyword"),
                    "last_scan_run_id": card.get("provenance", {}).get("last_scan_run_id"),
                    "source": card.get("provenance", {}).get("source"),
                }
                for card in cards[:12]
            ],
        }

    def _quality_gate(self, cards: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
        checks = [
            {
                "name": "has_keywords",
                "passed": bool(cards),
                "detail": f"{len(cards)} keyword cards",
            },
            {
                "name": "has_evidence_trace",
                "passed": metrics.get("evidence_trace_count", 0) >= len(cards),
                "detail": f"{metrics.get('evidence_trace_count', 0)} evidence items",
            },
            {
                "name": "confidence_calibrated",
                "passed": not cards or metrics.get("avg_confidence", 0) >= 0.58,
                "detail": f"average confidence {metrics.get('avg_confidence', 0)}",
            },
            {
                "name": "review_queue_visible",
                "passed": True,
                "detail": f"{metrics.get('human_review_required_count', 0)} items require human review",
            },
            {
                "name": "agent_contract_ready",
                "passed": bool(cards),
                "detail": "blog, shorts, viral, and ad packets include shared handoff fields",
            },
            {
                "name": "decision_states_declared",
                "passed": not cards or sum((metrics.get("decision_counts") or {}).values()) == len(cards),
                "detail": f"decision states {metrics.get('decision_counts', {})}",
            },
            {
                "name": "measurement_plan_ready",
                "passed": not cards or metrics.get("measurement_plan_count", 0) == len(cards),
                "detail": f"{metrics.get('measurement_plan_count', 0)} measurement plans",
            },
            {
                "name": "data_quality_visible",
                "passed": True,
                "detail": f"{metrics.get('data_quality_thin_count', 0)} thin data-quality cards",
            },
            {
                "name": "place_tracking_visible",
                "passed": True,
                "detail": (
                    f"{metrics.get('place_tracked_count', 0)} tracked, "
                    f"{metrics.get('place_declining_count', 0)} declining, "
                    f"{metrics.get('place_competitor_gap_count', 0)} competitor gaps"
                ),
            },
        ]
        if not cards:
            status = "empty"
        elif any(not check["passed"] for check in checks):
            status = "review"
        elif metrics.get("human_review_required_count", 0):
            status = "review"
        elif metrics.get("data_quality_thin_count", 0):
            status = "review"
        elif (metrics.get("decision_counts") or {}).get("hold", 0):
            status = "review"
        else:
            status = "pass"
        return {
            "status": status,
            "checks": checks,
            "required_before_publish": [
                "review all human_review.required items",
                "keep evidence_trace with generated content or campaign drafts",
                "do not use medical guarantees, competitor attacks, or review manipulation",
            ],
        }

    def _delivery_contract(self) -> Dict[str, Any]:
        return {
            "handoff_fields": [
                "handoff_id",
                "primary_keyword",
                "confidence",
                "confidence_band",
                "evidence_trace",
                "human_review",
                "feedback_snapshot",
                "decision_packet",
                "measurement_plan",
                "data_quality",
                "place_rank",
                "place_rank_lift",
                "place_value_loop",
                "place_value_brief",
                "place_lift_actions",
                "place_lift_experiments",
                "place_tracking_candidates",
                "place_profile_audit",
                "risk_guardrails",
                "success_criteria",
            ],
            "agent_packets": {
                "blog_agent": "produce evidence-backed outline, FAQ, and safe local intent copy",
                "shorts_studio_agent": "produce short-form hook and visual beats from explicit intent signals",
                "viral_hunter_agent": "listen for community questions and reply with verification-first guidance",
                "ad_agent": "test landing and ad messaging only after guardrail review",
            },
            "guardrails": [
                "preserve the handoff_id in downstream drafts",
                "cite or restate the evidence_trace that justifies the angle",
                "respect decision_packet.publish_policy before publishing",
                "measure outcome using measurement_plan.primary_metric",
                "when present, use place_rank to distinguish rank recovery, defense, and competitor-gap work",
                "use place_rank_lift priority_actions only within listed prohibited_tactics guardrails",
                "use place_value_loop to update SmartPlace fields only when the suggestion matches real services and evidence",
                "send low-confidence or risk-marked cards back to human review",
            ],
        }

    def _feedback_contract(self) -> Dict[str, Any]:
        return {
            "endpoint": "/pathfinder/insight-feedback",
            "method": "POST",
            "feedback_types": [
                "accepted",
                "rejected",
                "needs_review",
                "sent_to_agent",
                "completed",
                "failed",
            ],
            "minimum_payload": ["handoff_id", "feedback_type"],
        }

    def _codex_synthesis(
        self,
        *,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        action_queue: Sequence[Dict[str, Any]],
        place_tracking: Optional[Dict[str, Any]] = None,
        place_rank_lift: Optional[Dict[str, Any]] = None,
        place_value_loop: Optional[Dict[str, Any]] = None,
        requested: bool,
    ) -> Dict[str, Any]:
        fallback = self._deterministic_synthesis(
            cards=cards,
            metrics=metrics,
            place_tracking=place_tracking,
            place_rank_lift=place_rank_lift,
            place_value_loop=place_value_loop,
            action_queue=action_queue,
        )
        if not requested:
            return {
                **fallback,
                "status": "not_requested",
                "model": "deterministic_fallback",
            }
        if not cards:
            return {
                **fallback,
                "status": "empty",
                "model": "deterministic_fallback",
            }

        prompt_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card["keyword"],
                "grade": card["grade"],
                "category": card["category"],
                "intent": card["search_intent"],
                "insight_score": card["insight_score"],
                "confidence": card.get("confidence"),
                "confidence_band": card.get("confidence_band"),
                "why_it_matters": card["why_it_matters"],
                "risks": card["risks"],
                "evidence_trace": card.get("evidence_trace", [])[:8],
                "human_review": card.get("human_review", {}),
                "feedback_snapshot": card.get("feedback_snapshot", {}),
                "decision_packet": card.get("decision_packet", {}),
                "measurement_plan": card.get("measurement_plan", {}),
                "data_quality": card.get("data_quality", {}),
                "place_rank": card.get("place_rank", {}),
                "place_lift_actions": card.get("place_lift_actions", [])[:4],
                "place_lift_experiments": card.get("place_lift_experiments", [])[:2],
                "place_tracking_candidates": card.get("place_tracking_candidates", [])[:4],
                "place_profile_audit": card.get("place_profile_audit", [])[:5],
                "place_value_brief": card.get("place_value_brief", {}),
                "agent_notes": card["agent_notes"],
                "signals": card["signals"],
                "metrics": {
                    "business_value_score": card["metrics"].get("business_value_score", 0),
                    "longtail_score": card["metrics"].get("longtail_score", 0),
                    "search_volume": card["metrics"].get("search_volume", 0),
                    "local_surface_score": card["metrics"].get("local_surface_score", 0),
                    "payment_coverage_score": card["metrics"].get("payment_coverage_score", 0),
                    "access_convenience_score": card["metrics"].get("access_convenience_score", 0),
                    "availability_intent_score": card["metrics"].get("availability_intent_score", 0),
                    "review_surface_score": card["metrics"].get("review_surface_score", 0),
                },
            }
            for card in list(cards)[:8]
        ]
        prompt = f"""
You are Codex acting as a senior marketing strategist for a Korean medicine clinic.
Read the Pathfinder keyword insight cards and produce a concise Korean executive synthesis.

Return JSON only with this shape:
{{
  "executive_summary": "2-3 sentence Korean summary for the user",
  "decision": "what should be done first",
  "confidence": 0.0,
  "agent_routing": [
    {{"agent": "blog_agent", "priority": "high|medium|low", "instruction": "specific handoff"}},
    {{"agent": "shorts_studio_agent", "priority": "high|medium|low", "instruction": "specific handoff"}}
  ],
  "watchouts": ["guardrail 1", "guardrail 2"],
  "why_this_is_not_generic": "explain why these are insight-backed, not keyword stuffing"
}}

Metrics:
{json.dumps(metrics, ensure_ascii=False)}

Place tracking:
{json.dumps(place_tracking or {}, ensure_ascii=False)}

Place rank lift plan:
{json.dumps(place_rank_lift or {}, ensure_ascii=False)}

Place value loop:
{json.dumps(place_value_loop or {}, ensure_ascii=False)}

Action queue:
{json.dumps(list(action_queue)[:6], ensure_ascii=False)}

Keyword cards:
{json.dumps(prompt_cards, ensure_ascii=False)}
"""
        try:
            try:
                from services.ai_client import ai_generate_json
            except Exception:
                from marketing_bot_web.backend.services.ai_client import ai_generate_json

            result = ai_generate_json(
                prompt,
                temperature=0.2,
                max_tokens=1400,
                task="strategy",
            )
            if isinstance(result, dict) and result:
                return {
                    **fallback,
                    **result,
                    "status": "codex",
                    "model": "codex_cli",
                }
        except Exception as exc:
            fallback["error"] = str(exc)
        return {
            **fallback,
            "status": "fallback",
            "model": "deterministic_fallback",
        }

    def _deterministic_synthesis(
        self,
        *,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        action_queue: Sequence[Dict[str, Any]],
        place_tracking: Optional[Dict[str, Any]] = None,
        place_rank_lift: Optional[Dict[str, Any]] = None,
        place_value_loop: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not cards:
            return {
                "executive_summary": "최신 Pathfinder 인사이트가 아직 없습니다. Legion 모드를 실행해 검증된 키워드와 에이전트 handoff를 먼저 확보해야 합니다.",
                "decision": "Pathfinder Legion 실행",
                "confidence": 0.0,
                "agent_routing": [],
                "watchouts": [],
                "why_this_is_not_generic": "실행 가능한 키워드 카드가 없어 일반적인 조언만 가능합니다.",
            }

        top = cards[0]
        first_action = action_queue[0] if action_queue else top["recommended_actions"][0]
        summary_parts = [
            f"가장 높은 실행 우선순위는 '{top['keyword']}'입니다.",
            f"상위 후보 {len(cards)}개 중 고가치 롱테일은 {metrics.get('high_value_longtail_count', 0)}개입니다.",
        ]
        if metrics.get("access_intent_count", 0):
            summary_parts.append("방문 편의/접근성 신호가 있어 쇼츠와 플레이스형 콘텐츠로도 전달 가치가 큽니다.")
        if metrics.get("payment_intent_count", 0):
            summary_parts.append("비용/보험 신호는 FAQ형 블로그로 풀어야 전환 설명력이 높아집니다.")
        place = place_tracking or {}
        if place.get("declining_count", 0):
            summary_parts.append("플레이스 순위 하락 카드가 있어 복구 우선순위를 화면에서 바로 확인해야 합니다.")
        elif place.get("competitor_gap_count", 0):
            summary_parts.append("경쟁사가 앞선 플레이스 키워드는 차별화 메시지와 방어 콘텐츠가 필요합니다.")
        elif place.get("tracked_count", 0):
            summary_parts.append("최신 플레이스 추적 결과가 함께 전달되어 키워드 실행과 순위 방어를 같이 판단할 수 있습니다.")

        lift = place_rank_lift or {}
        if lift.get("priority_actions"):
            first_lift = lift["priority_actions"][0]
            summary_parts.append(
                f"플레이스 리프트는 '{first_lift.get('title')}'를 우선 실행하고 조작성 수단은 차단합니다."
            )
        value_loop = place_value_loop or {}
        rep_keywords = (
            (value_loop.get("pathfinder_to_place") or {})
            .get("representative_keyword_candidates", [])
        )
        if rep_keywords:
            summary_parts.append(
                f"스마트플레이스에는 대표키워드 후보 {len(rep_keywords)}개와 FAQ/사진/리뷰 응답 보강안을 환류할 수 있습니다."
            )

        routing = []
        for action in list(action_queue)[:4]:
            routing.append({
                "agent": action.get("owner", ""),
                "priority": action.get("priority", "medium"),
                "instruction": f"{action.get('keyword', '')}: {action.get('angle', '')}",
            })

        watchouts: List[str] = []
        for card in cards[:5]:
            watchouts.extend(card.get("risks") or [])
        watchouts.extend((place_rank_lift or {}).get("prohibited_tactics", [])[:3])
        watchouts = list(dict.fromkeys(watchouts))[:4]

        return {
            "executive_summary": " ".join(summary_parts),
            "decision": f"{first_action.get('owner', 'blog_agent')}에서 '{first_action.get('keyword', top['keyword'])}' 실행",
            "confidence": round(float(metrics.get("avg_confidence") or top.get("confidence") or 0.0), 2),
            "agent_routing": routing,
            "watchouts": watchouts,
            "place_rank_lift": {
                "headline": (place_rank_lift or {}).get("headline"),
                "diagnostic_scores": (place_rank_lift or {}).get("diagnostic_scores", {}),
                "priority_actions": (place_rank_lift or {}).get("priority_actions", [])[:3],
                "experiment_queue": (place_rank_lift or {}).get("experiment_queue", [])[:2],
                "tracking_expansion": (place_rank_lift or {}).get("tracking_expansion", {}),
            },
            "place_value_loop": {
                "headline": (place_value_loop or {}).get("headline"),
                "representative_keyword_candidates": rep_keywords[:5],
                "smartplace_updates": ((place_value_loop or {}).get("pathfinder_to_place") or {}).get("smartplace_updates", [])[:3],
                "import_signals": ((place_value_loop or {}).get("place_to_pathfinder") or {}).get("import_signals", [])[:3],
            },
            "why_this_is_not_generic": "Pathfinder의 사업가치, 롱테일, 로컬/예약/비용/접근성/리뷰 신호와 가드레일을 함께 사용해 생성된 실행 브리프입니다.",
        }

    def _build_action_queue(self, cards: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        queue: List[Dict[str, Any]] = []
        for card in cards[:6]:
            for action in card["recommended_actions"]:
                item = dict(action)
                item["handoff_id"] = card.get("handoff_id")
                item["insight_score"] = card["insight_score"]
                item["confidence"] = card.get("confidence")
                item["confidence_band"] = card.get("confidence_band")
                item["human_review"] = card.get("human_review", {})
                item["feedback_snapshot"] = card.get("feedback_snapshot", {})
                item["decision_packet"] = card.get("decision_packet", {})
                item["measurement_plan"] = card.get("measurement_plan", {})
                item["data_quality"] = card.get("data_quality", {})
                item["place_rank"] = card.get("place_rank", {})
                item["place_value_brief"] = card.get("place_value_brief", {})
                item["evidence_trace"] = card.get("evidence_trace", [])[:6]
                item["rationale"] = card["why_it_matters"][:3]
                queue.append(item)
        queue.sort(key=lambda item: (item["priority"] != "high", -item["insight_score"]))
        return queue[:10]

    def _support_keywords(self, cards: Sequence[Dict[str, Any]], card: Dict[str, Any]) -> List[str]:
        same_category = [
            other["keyword"]
            for other in cards
            if other["keyword"] != card["keyword"] and other["category"] == card["category"]
        ]
        return same_category[:4]

    def _task_contract(self, card: Dict[str, Any], agent: str) -> Dict[str, Any]:
        return {
            "handoff_id": card.get("handoff_id"),
            "confidence": card.get("confidence"),
            "confidence_band": card.get("confidence_band"),
            "human_review": card.get("human_review", {}),
            "feedback_snapshot": card.get("feedback_snapshot", {}),
            "decision_packet": card.get("decision_packet", {}),
            "measurement_plan": card.get("measurement_plan", {}),
            "data_quality": card.get("data_quality", {}),
            "place_rank": card.get("place_rank", {}),
            "place_lift_actions": card.get("place_lift_actions", [])[:4],
            "place_lift_experiments": card.get("place_lift_experiments", [])[:2],
            "place_tracking_candidates": card.get("place_tracking_candidates", [])[:4],
            "place_profile_audit": card.get("place_profile_audit", [])[:5],
            "place_value_brief": card.get("place_value_brief", {}),
            "evidence_trace": card.get("evidence_trace", [])[:8],
            "risk_guardrails": card.get("risks", []),
            "success_criteria": self._success_criteria(card, agent),
        }

    def _success_criteria(self, card: Dict[str, Any], agent: str) -> List[str]:
        criteria = [
            "uses the primary keyword naturally without stuffing",
            "preserves the handoff_id for traceability",
            "reflects at least two evidence_trace signals in the output",
        ]
        if card.get("human_review", {}).get("required"):
            criteria.append("waits for human review before publishing or running ads")
        if card.get("place_lift_actions"):
            criteria.append("reflects place_lift_actions without click, booking, or review manipulation")
        if card.get("place_tracking_candidates"):
            criteria.append("keeps place_tracking_candidates as measurement inputs, not keyword stuffing targets")
        if card.get("place_value_brief"):
            criteria.append("turns Pathfinder insight into SmartPlace profile value without fake reviews or profile keyword stuffing")
        if agent == "blog_agent":
            criteria.append("turns intent into an outline, FAQ, and safe CTA")
        elif agent == "shorts_studio_agent":
            criteria.append("turns explicit intent into a hook and visual beats")
        elif agent == "viral_hunter_agent":
            criteria.append("answers community demand with verification-first wording")
        elif agent == "ad_agent":
            criteria.append("separates landing-page proof from ad copy claims")
        return criteria

    def _blog_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        for card in cards:
            action = card["recommended_actions"][0]
            tasks.append({
                **self._task_contract(card, "blog_agent"),
                "primary_keyword": card["keyword"],
                "category": card["category"],
                "angle": action["angle"],
                "support_keywords": self._support_keywords(cards, card),
                "must_include": action["must_include"],
                "avoid": action["avoid"],
                "evidence": card["why_it_matters"],
            })
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="blog_agent")}

    def _shorts_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        for card in cards:
            action = card["recommended_actions"][1]
            tasks.append({
                **self._task_contract(card, "shorts_studio_agent"),
                "primary_keyword": card["keyword"],
                "hook": action["angle"],
                "visual_beats": self._shorts_visual_beats(card),
                "must_include": action["must_include"],
                "avoid": action["avoid"],
            })
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="shorts_studio_agent")}

    def _shorts_visual_beats(self, card: Dict[str, Any]) -> List[str]:
        signal = card["signals"]
        if signal["access_convenience_type"] != "none":
            return ["외부/주차 컷", "입구 또는 접수 동선", "방문 전 체크 문구"]
        if signal["availability_intent_type"] != "none":
            return ["시계 또는 예약 화면", "대기/접수 상황", "빠른 문의 CTA"]
        if signal["payment_coverage_type"] != "none":
            return ["서류 체크리스트", "보험/비용 질문 자막", "상담 전 확인 CTA"]
        return ["검색 질문 자막", "핵심 설명 컷", "방문 전 확인 CTA"]

    def _viral_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = [{
            **self._task_contract(card, "viral_hunter_agent"),
            "keyword": card["keyword"],
            "listening_angle": "질문형 글과 댓글에서 정보 부족/방문 전 불안을 찾기",
            "reply_guidance": card["agent_notes"]["viral_hunter_agent"],
            "risk_guardrails": card["risks"],
        } for card in cards]
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="viral_hunter_agent")}

    def _ad_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = [{
            **self._task_contract(card, "ad_agent"),
            "keyword": card["keyword"],
            "test_idea": card["agent_notes"]["ad_agent"],
            "landing_focus": card["recommended_actions"][0]["angle"],
            "risk_guardrails": card["risks"],
        } for card in cards]
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="ad_agent")}


def load_pathfinder_prompt_context(
    db_path: str,
    *,
    agent: str = "all",
    topic: Optional[str] = None,
    limit: int = 5,
) -> str:
    """Convenience helper for legacy agents that only accept prompt text."""
    try:
        broker = PathfinderInsightBroker(db_path)
        cards = broker.keyword_cards(limit=limit)
        if topic:
            topic_norm = topic.replace(" ", "").lower()
            filtered = [
                card for card in cards
                if topic_norm in card["keyword"].replace(" ", "").lower()
                or card["keyword"].replace(" ", "").lower() in topic_norm
            ]
            if filtered:
                cards = filtered + [card for card in cards if card not in filtered]
        return broker.format_prompt_context(cards=cards, agent=AGENT_ALIASES.get(agent, agent), topic=topic, limit=limit)
    except Exception as exc:
        return f"[Pathfinder Insight Handoff unavailable: {exc}]"
