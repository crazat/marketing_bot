"""
Automation Handlers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

이벤트 기반 자동화 핸들러
- S/A급 키워드 발굴 시 순위 추적 자동 등록
- Hot 리드 발견 시 알림 생성
- 경쟁사 변동 시 알림 생성
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, Any

from .event_bus import event_bus, Event, EventType, on_event
from db.database import DatabaseManager

logger = logging.getLogger(__name__)


def get_db_path():
    """DatabaseManager에서 db_path 가져오기"""
    return DatabaseManager().db_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 키워드 관련 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@on_event(EventType.KEYWORD_APPROVED)
async def handle_keyword_approved(event: Event):
    """
    S/A급 키워드 승인 시 자동 순위 추적 등록
    """
    keyword = event.data.get("keyword")
    grade = event.data.get("grade")

    if not keyword:
        return

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # keywords.json에 이미 있는지 확인
        import os
        from pathlib import Path

        # config 경로 찾기
        backend_dir = Path(__file__).parent.parent
        project_root = backend_dir.parent.parent
        keywords_path = project_root / "config" / "keywords.json"

        if keywords_path.exists():
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)

            naver_place = keywords_data.get("naver_place", [])

            # 이미 등록되어 있으면 스킵
            if keyword in naver_place:
                logger.info(f"[자동 연동] 키워드 '{keyword}' 이미 순위 추적 중")
                conn.close()
                return

            # 새 키워드 추가
            naver_place.append(keyword)
            keywords_data["naver_place"] = naver_place

            with open(keywords_path, 'w', encoding='utf-8') as f:
                json.dump(keywords_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[자동 연동] {grade}급 키워드 '{keyword}' 순위 추적 등록 완료")

            # 알림 생성
            await create_notification(
                title=f"{grade}급 키워드 순위 추적 등록",
                message=f"'{keyword}' 키워드가 자동으로 순위 추적에 등록되었습니다.",
                notification_type="keyword",
                severity="info",
                reference_keyword=keyword,
                link="/battle"
            )

        conn.close()

    except Exception as e:
        logger.error(f"[자동 연동] 키워드 순위 추적 등록 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 리드 관련 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@on_event(EventType.LEAD_HOT_DETECTED)
async def handle_hot_lead_detected(event: Event):
    """
    Hot 리드 발견 시 알림 생성 및 우선순위 설정
    """
    lead_id = event.data.get("lead_id")
    score = event.data.get("score")
    platform = event.data.get("platform", "unknown")
    keyword = event.data.get("keyword")

    if not lead_id:
        return

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 리드 정보 조회
        cursor.execute("""
            SELECT title, author, content FROM mentions WHERE id = ?
        """, (lead_id,))
        row = cursor.fetchone()

        title = row[0] if row else "제목 없음"
        author = row[1] if row else "익명"
        content_preview = (row[2][:50] + "...") if row and len(row[2]) > 50 else (row[2] if row else "")

        # 알림 생성
        await create_notification(
            title=f"🔥 Hot 리드 발견! (점수: {score})",
            message=f"[{platform}] {author}: {title[:30]}...",
            notification_type="lead",
            severity="critical",
            reference_keyword=keyword,
            link=f"/leads?id={lead_id}"
        )

        logger.info(f"[자동 연동] Hot 리드 #{lead_id} 알림 생성 (점수: {score})")

        conn.close()

    except Exception as e:
        logger.error(f"[자동 연동] Hot 리드 알림 생성 오류: {e}")


@on_event(EventType.LEAD_CONVERTED)
async def handle_lead_converted(event: Event):
    """
    리드 전환 시 통계 업데이트
    """
    lead_id = event.data.get("lead_id")
    keyword = event.data.get("keyword")
    revenue = event.data.get("revenue", 0)

    if not lead_id:
        return

    try:
        # 키워드 라이프사이클 업데이트
        if keyword:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE keyword_lifecycle
                SET total_conversions = total_conversions + 1,
                    total_revenue = total_revenue + ?,
                    last_conversion_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE keyword = ?
            """, (revenue, keyword))

            conn.commit()
            conn.close()

            logger.info(f"[자동 연동] 키워드 '{keyword}' 전환 통계 업데이트")

    except Exception as e:
        logger.error(f"[자동 연동] 리드 전환 처리 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 순위 관련 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@on_event(EventType.RANK_DROPPED)
async def handle_rank_dropped(event: Event):
    """
    순위 하락 시 알림 생성
    """
    keyword = event.data.get("keyword")
    new_rank = event.data.get("new_rank")
    prev_rank = event.data.get("prev_rank")
    change = event.data.get("change", 0)

    if not keyword or change < 3:  # 3순위 이상 하락만 알림
        return

    try:
        severity = "critical" if change >= 5 else "warning"

        await create_notification(
            title=f"⚠️ 순위 하락 경고: {keyword}",
            message=f"{prev_rank}위 → {new_rank}위 ({change}순위 하락)",
            notification_type="rank",
            severity=severity,
            reference_keyword=keyword,
            link=f"/battle?keyword={keyword}"
        )

        logger.info(f"[자동 연동] '{keyword}' 순위 하락 알림 ({change}순위)")

    except Exception as e:
        logger.error(f"[자동 연동] 순위 하락 알림 오류: {e}")


@on_event(EventType.RANK_TOP10_ENTERED)
async def handle_top10_entered(event: Event):
    """
    Top 10 진입 시 축하 알림
    """
    keyword = event.data.get("keyword")
    rank = event.data.get("rank")

    if not keyword:
        return

    try:
        await create_notification(
            title=f"🎉 Top 10 진입: {keyword}",
            message=f"'{keyword}' 키워드가 {rank}위로 Top 10에 진입했습니다!",
            notification_type="rank",
            severity="info",
            reference_keyword=keyword,
            link=f"/battle?keyword={keyword}"
        )

        logger.info(f"[자동 연동] '{keyword}' Top 10 진입 알림 ({rank}위)")

    except Exception as e:
        logger.error(f"[자동 연동] Top 10 진입 알림 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 경쟁사 관련 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@on_event(EventType.COMPETITOR_RANK_SURGE)
async def handle_competitor_rank_surge(event: Event):
    """
    경쟁사 순위 급상승 시 알림 생성
    """
    competitor = event.data.get("competitor")
    keyword = event.data.get("keyword")
    new_rank = event.data.get("new_rank")
    prev_rank = event.data.get("prev_rank")
    change = event.data.get("change", 0)

    if not competitor or change < 3:
        return

    try:
        severity = "critical" if change >= 5 else "warning"

        await create_notification(
            title=f"🔴 경쟁사 급상승: {competitor}",
            message=f"'{keyword}' 키워드에서 {prev_rank}위 → {new_rank}위 ({change}순위 상승)",
            notification_type="competitor",
            severity=severity,
            reference_keyword=keyword,
            link=f"/battle?keyword={keyword}"
        )

        logger.info(f"[자동 연동] 경쟁사 '{competitor}' 급상승 알림 ({change}순위)")

    except Exception as e:
        logger.error(f"[자동 연동] 경쟁사 급상승 알림 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 바이럴 관련 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@on_event(EventType.VIRAL_COMMENT_COMPLETED)
async def handle_viral_comment_completed(event: Event):
    """
    바이럴 댓글 완료 시 통계 업데이트
    """
    viral_id = event.data.get("viral_id")
    keyword = event.data.get("keyword")

    if not viral_id:
        return

    try:
        # 키워드 라이프사이클 업데이트
        if keyword:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE keyword_lifecycle
                SET last_viral_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE keyword = ?
            """, (keyword,))

            conn.commit()
            conn.close()

        logger.info(f"[자동 연동] 바이럴 #{viral_id} 완료 처리")

    except Exception as e:
        logger.error(f"[자동 연동] 바이럴 완료 처리 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 알림 생성 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def create_notification(
    title: str,
    message: str,
    notification_type: str = "system",
    severity: str = "info",
    reference_keyword: str = None,
    link: str = None
):
    """알림 생성 및 저장"""
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # severity를 priority로 매핑 (info→medium, warning→high, critical→critical)
        priority_map = {
            "info": "medium",
            "warning": "high",
            "critical": "critical",
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        priority = priority_map.get(severity, "medium")

        cursor.execute("""
            INSERT INTO notifications (title, message, type, priority, reference_keyword, link, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now'))
        """, (title, message, notification_type, priority, reference_keyword, link))

        conn.commit()
        notification_id = cursor.lastrowid
        conn.close()

        logger.info(f"[알림] #{notification_id} 생성: {title}")

        # WebSocket으로 실시간 알림 전송 (선택적)
        try:
            from .websocket_manager import ws_manager
            await ws_manager.broadcast({
                "type": "notification",
                "data": {
                    "id": notification_id,
                    "title": title,
                    "message": message,
                    "severity": severity,
                    "link": link,
                }
            })
        except Exception as ws_error:
            logger.debug(f"WebSocket 알림 전송 스킵: {ws_error}")

        return notification_id

    except Exception as e:
        logger.error(f"[알림] 생성 오류: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 핸들러 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def initialize_handlers():
    """핸들러 초기화 (앱 시작 시 호출)"""
    # @on_event 데코레이터로 이미 등록됨
    subscriber_count = event_bus.get_subscriber_count()
    logger.info(f"[자동화] 이벤트 핸들러 초기화 완료: {subscriber_count}")
    return subscriber_count
