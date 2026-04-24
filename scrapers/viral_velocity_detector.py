#!/usr/bin/env python3
"""
Viral Velocity Detector
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-3] 바이럴 속도 감지기

커뮤니티 멘션 데이터의 시간당 발생 빈도를 추적하고
이동 평균 대비 3σ 초과 시 바이럴 스파이크로 판정하여 즉시 알림

데이터 소스: community_mentions 테이블 (naver_api_community_monitor.py 수집)

실행:
    python scrapers/viral_velocity_detector.py
    python scrapers/viral_velocity_detector.py --threshold 2.5  # z-score 임계값 조정
"""

import sys
import os
import sqlite3
import json
import math
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Sentry
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("viral_velocity_detector")
except Exception:
    pass

from db.database import DatabaseManager
from utils import logger

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


def calculate_velocity(
    db_path: str,
    hours_window: int = 24,
    lookback_days: int = 14,
    z_threshold: float = 3.0,
) -> List[Dict[str, Any]]:
    """
    키워드별 멘션 속도를 계산하고 스파이크를 감지합니다.

    Args:
        db_path: DB 경로
        hours_window: 현재 시간 윈도우 (시간 단위, 기본 24시간)
        lookback_days: 이동 평균 계산을 위한 과거 데이터 기간 (일)
        z_threshold: 스파이크 판정 z-score 임계값 (기본 3.0)

    Returns:
        스파이크가 감지된 키워드 목록
    """
    conn = None
    spikes = []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # community_mentions 테이블 존재 확인
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='community_mentions'"
        )
        if not cursor.fetchone():
            logger.warning("community_mentions 테이블이 없습니다.")
            return []

        # 키워드별 최근 N시간 멘션 수
        cursor.execute("""
            SELECT keyword, COUNT(*) as recent_count
            FROM community_mentions
            WHERE created_at >= datetime('now', ? || ' hours')
            GROUP BY keyword
            HAVING recent_count > 0
            ORDER BY recent_count DESC
        """, (f"-{hours_window}",))

        recent_counts = {row['keyword']: row['recent_count'] for row in cursor.fetchall()}

        if not recent_counts:
            logger.info("최근 멘션 데이터가 없습니다.")
            return []

        # 키워드별 과거 일일 평균 및 표준편차 계산
        for keyword, current_count in recent_counts.items():
            cursor.execute("""
                SELECT
                    date(created_at) as day,
                    COUNT(*) as daily_count
                FROM community_mentions
                WHERE keyword = ?
                  AND created_at >= datetime('now', ? || ' days')
                  AND created_at < datetime('now', ? || ' hours')
                GROUP BY date(created_at)
            """, (keyword, f"-{lookback_days}", f"-{hours_window}"))

            daily_counts = [row['daily_count'] for row in cursor.fetchall()]

            if len(daily_counts) < 3:
                # 데이터가 너무 적으면 스킵 (최소 3일)
                continue

            # 이동 평균 및 표준편차
            mean = sum(daily_counts) / len(daily_counts)
            variance = sum((x - mean) ** 2 for x in daily_counts) / len(daily_counts)
            std_dev = math.sqrt(variance) if variance > 0 else 0.001

            # 현재 윈도우를 일 단위로 환산하여 비교
            normalized_count = current_count * (24 / hours_window)
            z_score = (normalized_count - mean) / std_dev if std_dev > 0 else 0

            is_spike = z_score >= z_threshold

            # 스파이크 시 샘플 URL 수집
            sample_urls = []
            if is_spike:
                cursor.execute("""
                    SELECT url, title FROM community_mentions
                    WHERE keyword = ?
                      AND created_at >= datetime('now', ? || ' hours')
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (keyword, f"-{hours_window}"))
                sample_urls = [
                    {"url": row['url'], "title": row['title']}
                    for row in cursor.fetchall()
                ]

            velocity_data = {
                "keyword": keyword,
                "platform": "all",
                "time_window": f"{hours_window}h",
                "mention_count": current_count,
                "moving_average": round(mean, 2),
                "std_deviation": round(std_dev, 2),
                "z_score": round(z_score, 2),
                "spike_detected": is_spike,
                "spike_magnitude": round(z_score, 2) if is_spike else 0,
                "sample_urls": sample_urls,
            }

            # DB 저장
            cursor.execute("""
                INSERT INTO viral_velocity
                (keyword, platform, time_window, mention_count, moving_average,
                 std_deviation, z_score, spike_detected, spike_magnitude, sample_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                keyword, "all", f"{hours_window}h", current_count,
                round(mean, 2), round(std_dev, 2), round(z_score, 2),
                is_spike, round(z_score, 2) if is_spike else 0,
                json.dumps(sample_urls, ensure_ascii=False),
            ))

            if is_spike:
                spikes.append(velocity_data)
                logger.warning(
                    f"🔥 SPIKE: '{keyword}' - "
                    f"현재 {current_count}건 (평균 {mean:.1f}, z={z_score:.1f})"
                )

        conn.commit()
        logger.info(
            f"✅ Velocity 분석 완료: {len(recent_counts)}개 키워드, "
            f"{len(spikes)}개 스파이크 감지"
        )

    except Exception as e:
        logger.error(f"Velocity 분석 오류: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return spikes


def send_spike_alerts(spikes: List[Dict[str, Any]]):
    """
    스파이크 감지 시 텔레그램 P1 알림 전송
    """
    if not spikes:
        return

    try:
        from alert_bot import send_telegram_message
    except ImportError:
        logger.warning("alert_bot을 import할 수 없습니다. 텔레그램 알림 스킵.")
        return

    for spike in spikes:
        keyword = spike['keyword']
        count = spike['mention_count']
        z = spike['z_score']
        avg = spike['moving_average']
        urls = spike.get('sample_urls', [])

        url_lines = "\n".join(
            f"  • {u.get('title', '제목 없음')[:40]}"
            for u in urls[:3]
        ) if urls else "  (샘플 없음)"

        message = (
            f"🔥 바이럴 스파이크 감지\n\n"
            f"키워드: {keyword}\n"
            f"현재 멘션: {count}건\n"
            f"평균: {avg:.1f}건 (z-score: {z:.1f})\n\n"
            f"최근 게시글:\n{url_lines}"
        )

        try:
            send_telegram_message(message)
            logger.info(f"📨 스파이크 알림 전송: {keyword}")
        except Exception as e:
            logger.error(f"텔레그램 알림 전송 실패: {e}")


def run_velocity_check(z_threshold: float = 3.0, hours_window: int = 24):
    """메인 실행 함수"""
    print(f"🔍 Viral Velocity Detector 시작 (z-threshold={z_threshold}, window={hours_window}h)")

    db = DatabaseManager()
    spikes = calculate_velocity(
        db_path=db.db_path,
        hours_window=hours_window,
        z_threshold=z_threshold,
    )

    if spikes:
        print(f"\n🔥 {len(spikes)}개 스파이크 감지!")
        for s in spikes:
            print(f"  • {s['keyword']}: {s['mention_count']}건 (z={s['z_score']:.1f})")
        send_spike_alerts(spikes)
    else:
        print("✅ 스파이크 없음 - 정상 범위")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Viral Velocity Detector")
    parser.add_argument("--threshold", type=float, default=3.0, help="z-score 임계값 (기본: 3.0)")
    parser.add_argument("--window", type=int, default=24, help="시간 윈도우 (기본: 24시간)")
    args = parser.parse_args()

    run_velocity_check(z_threshold=args.threshold, hours_window=args.window)
