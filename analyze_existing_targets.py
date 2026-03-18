#!/usr/bin/env python3
"""
기존 DB의 viral targets에 대해 AI 분석 실행

- 경쟁사 탐지
- 침투적합도 평가
- 부적합한 타겟 필터링
"""

import sys
import os
from typing import List
from dataclasses import dataclass, field
import hashlib

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viral_hunter import ViralTarget, AICommentGenerator
from db.database import DatabaseManager
from utils import logger


def load_targets_from_db() -> List[ViralTarget]:
    """
    DB에서 pending 상태의 타겟들을 ViralTarget 객체로 변환
    """
    db = DatabaseManager()

    # pending 상태의 타겟만 조회 (AI 분석 대상)
    raw_targets = db.get_viral_targets(limit=100000)

    targets = []
    for row in raw_targets:
        # comment_status가 pending인 것만
        if row.get('comment_status') != 'pending':
            continue

        # ViralTarget 객체 생성
        try:
            # matched_keyword 문자열을 리스트로 변환
            matched_keywords_str = row.get('matched_keyword', '')
            if matched_keywords_str:
                matched_keywords = [kw.strip() for kw in matched_keywords_str.split(',')]
            else:
                matched_keywords = []

            target = ViralTarget(
                platform=row.get('platform', 'unknown'),
                url=row.get('url', ''),
                title=row.get('title', ''),
                content_preview=row.get('content_preview', ''),
                matched_keywords=matched_keywords,
                category=row.get('category', '기타'),
                is_commentable=row.get('is_commentable', True),
                generated_comment=row.get('generated_comment', ''),
                priority_score=row.get('priority_score', 0.0),
                author=row.get('author', ''),
                date_str=row.get('date_str', '')
            )
            targets.append(target)
        except Exception as e:
            logger.warning(f"타겟 변환 실패: {e} | {row.get('url', 'N/A')}")
            continue

    logger.info(f"✅ DB에서 {len(targets)}개 타겟 로드 완료")
    return targets


def update_targets_in_db(suitable_targets: List[ViralTarget], unsuitable_count: int):
    """
    AI 분석 결과를 DB에 업데이트

    Args:
        suitable_targets: AI 분석 통과한 타겟들
        unsuitable_count: 부적합 판정된 타겟 수
    """
    db = DatabaseManager()

    # 적합한 타겟의 URL 세트
    suitable_urls = {t.url for t in suitable_targets}

    # 모든 pending 타겟 조회
    all_pending = db.get_viral_targets(limit=100000)

    skipped_count = 0
    for row in all_pending:
        if row.get('comment_status') != 'pending':
            continue

        url = row.get('url')

        # 부적합 타겟은 skipped로 변경
        if url and url not in suitable_urls:
            try:
                # comment_status를 'skipped'로 업데이트
                db.conn.execute(
                    "UPDATE viral_targets SET comment_status = 'skipped' WHERE url = ?",
                    (url,)
                )
                skipped_count += 1
            except Exception as e:
                logger.warning(f"업데이트 실패: {e} | {url}")

    db.conn.commit()
    logger.info(f"✅ DB 업데이트 완료: {skipped_count}개 타겟을 skipped로 변경")


def main():
    print("\n" + "="*60)
    print("🔬 기존 타겟 AI 분석 시작")
    print("="*60 + "\n")

    # 1. DB에서 타겟 로드
    print("📊 1단계: DB에서 타겟 로드 중...")
    targets = load_targets_from_db()

    if not targets:
        print("❌ 분석할 타겟이 없습니다.")
        return

    print(f"   ✅ {len(targets)}개 타겟 로드 완료\n")

    # 2. AI 분석 실행
    print("🔬 2단계: AI 통합 분석 실행 중...")
    print("   (경쟁사 탐지 + 침투적합도 평가)")
    print(f"   배치 크기: 25개")
    print(f"   예상 소요: {(len(targets) // 25) * 1}분\n")

    generator = AICommentGenerator()

    if not generator.client:
        print("❌ AI 모델이 초기화되지 않았습니다.")
        print("   Gemini API 키를 확인해주세요.")
        return

    suitable_targets = generator.unified_analysis(targets, batch_size=25)

    unsuitable_count = len(targets) - len(suitable_targets)

    print(f"\n✅ AI 분석 완료!")
    print(f"   전체: {len(targets)}개")
    print(f"   적합: {len(suitable_targets)}개")
    print(f"   부적합: {unsuitable_count}개")
    print(f"   적합률: {(len(suitable_targets) / len(targets) * 100):.1f}%\n")

    # 3. DB 업데이트
    if unsuitable_count > 0:
        print("💾 3단계: DB 업데이트 중...")
        update_targets_in_db(suitable_targets, unsuitable_count)
        print()

    # 4. 결과 요약
    print("="*60)
    print("✅ 분석 완료!")
    print("="*60)
    print(f"총 타겟: {len(targets)}개")
    print(f"AI 분석 통과: {len(suitable_targets)}개")
    print(f"부적합 판정: {unsuitable_count}개 (skipped 상태로 변경)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
