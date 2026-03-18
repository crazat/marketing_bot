"""
Cross-Platform Lead Deduplicator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3.1] 크로스 플랫폼 중복 제거 서비스

동일 콘텐츠가 여러 플랫폼에서 수집되는 경우를 처리:
- 콘텐츠 해시 기반 유사도 계산
- 클러스터링을 통한 중복 그룹화
- 대표 리드 선택 (가장 높은 점수)
- 관련 플랫폼 정보 메타데이터로 보존
"""

import hashlib
import re
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DeduplicatedLead:
    """중복 제거된 리드"""
    lead: Dict[str, Any]
    related_platforms: List[str] = field(default_factory=list)
    duplicate_count: int = 0
    total_reach: int = 0
    cluster_id: str = ""


class CrossPlatformDeduplicator:
    """
    크로스 플랫폼 중복 제거기

    동일/유사 콘텐츠를 감지하고 대표 리드만 선택합니다.

    알고리즘:
    1. 콘텐츠 정규화 (공백, 특수문자 제거)
    2. 해시 기반 완전 일치 감지
    3. Jaccard 유사도 기반 유사 콘텐츠 감지
    4. 클러스터별 대표 리드 선택
    """

    def __init__(self, similarity_threshold: float = 0.7):
        """
        Args:
            similarity_threshold: 유사도 임계값 (0.0~1.0, 기본 0.7)
        """
        self.similarity_threshold = similarity_threshold
        self._hash_cache: Dict[str, str] = {}

    def deduplicate(self, leads: List[Dict[str, Any]]) -> List[DeduplicatedLead]:
        """
        리드 목록에서 중복을 제거하고 대표 리드 반환

        Args:
            leads: 원본 리드 목록

        Returns:
            중복 제거된 DeduplicatedLead 목록
        """
        if not leads:
            return []

        # 1. 콘텐츠 해시 생성
        lead_hashes = []
        for lead in leads:
            content = self._extract_content(lead)
            content_hash = self._hash_content(content)
            normalized = self._normalize_content(content)
            lead_hashes.append({
                'lead': lead,
                'hash': content_hash,
                'normalized': normalized,
                'words': set(normalized.split()) if normalized else set()
            })

        # 2. 완전 일치 그룹화 (해시 기반)
        hash_groups: Dict[str, List[int]] = defaultdict(list)
        for idx, item in enumerate(lead_hashes):
            hash_groups[item['hash']].append(idx)

        # 3. 유사도 기반 클러스터링
        clusters = self._cluster_by_similarity(lead_hashes, hash_groups)

        # 4. 각 클러스터에서 대표 선택
        results = []
        for cluster_id, indices in clusters.items():
            cluster_leads = [lead_hashes[i]['lead'] for i in indices]
            representative = self._select_representative(cluster_leads)

            # 관련 플랫폼 수집
            platforms = list(set(
                lead.get('platform', 'unknown')
                for lead in cluster_leads
            ))

            # 총 도달 범위 계산
            total_reach = sum(
                lead.get('engagement', 0) or
                lead.get('like_count', 0) or
                lead.get('comment_count', 0) or 0
                for lead in cluster_leads
            )

            results.append(DeduplicatedLead(
                lead=representative,
                related_platforms=[p for p in platforms if p != representative.get('platform')],
                duplicate_count=len(cluster_leads) - 1,
                total_reach=total_reach,
                cluster_id=cluster_id
            ))

        # 점수순 정렬
        results.sort(
            key=lambda x: x.lead.get('priority_score', 0) or x.lead.get('score', 0),
            reverse=True
        )

        original_count = len(leads)
        deduped_count = len(results)
        removed_count = original_count - deduped_count

        logger.info(
            f"✅ 중복 제거 완료: {original_count}개 → {deduped_count}개 "
            f"(-{removed_count}개, {removed_count/original_count*100:.1f}% 감소)"
        )

        return results

    def _extract_content(self, lead: Dict[str, Any]) -> str:
        """리드에서 콘텐츠 추출"""
        title = lead.get('title', '') or ''
        content = (
            lead.get('content', '') or
            lead.get('content_preview', '') or
            lead.get('summary', '') or ''
        )
        return f"{title} {content}"

    def _normalize_content(self, content: str) -> str:
        """콘텐츠 정규화 (공백, 특수문자 제거)"""
        if not content:
            return ""

        # 소문자 변환
        content = content.lower()

        # 특수문자 제거 (한글, 영문, 숫자만 유지)
        content = re.sub(r'[^\w가-힣\s]', '', content)

        # 연속 공백 제거
        content = re.sub(r'\s+', ' ', content).strip()

        return content

    def _hash_content(self, content: str) -> str:
        """콘텐츠 해시 생성"""
        normalized = self._normalize_content(content)
        if not normalized:
            return "empty"

        # 캐시 확인
        if normalized in self._hash_cache:
            return self._hash_cache[normalized]

        # MD5 해시 (빠른 비교용)
        content_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()
        self._hash_cache[normalized] = content_hash

        return content_hash

    def _calculate_jaccard_similarity(self, words1: Set[str], words2: Set[str]) -> float:
        """Jaccard 유사도 계산"""
        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _cluster_by_similarity(
        self,
        lead_hashes: List[Dict],
        hash_groups: Dict[str, List[int]]
    ) -> Dict[str, List[int]]:
        """유사도 기반 클러스터링"""
        clusters: Dict[str, List[int]] = {}
        assigned: Set[int] = set()
        cluster_counter = 0

        # 1. 완전 일치 그룹 먼저 처리
        for hash_val, indices in hash_groups.items():
            if len(indices) > 0:
                cluster_id = f"cluster_{cluster_counter}"
                clusters[cluster_id] = indices.copy()
                assigned.update(indices)
                cluster_counter += 1

        # 2. 유사도 기반 병합
        cluster_list = list(clusters.items())
        merged = set()

        for i, (cid1, indices1) in enumerate(cluster_list):
            if cid1 in merged:
                continue

            for j, (cid2, indices2) in enumerate(cluster_list[i+1:], i+1):
                if cid2 in merged:
                    continue

                # 클러스터 대표 콘텐츠 비교
                rep1_idx = indices1[0]
                rep2_idx = indices2[0]

                words1 = lead_hashes[rep1_idx]['words']
                words2 = lead_hashes[rep2_idx]['words']

                similarity = self._calculate_jaccard_similarity(words1, words2)

                if similarity >= self.similarity_threshold:
                    # 클러스터 병합
                    clusters[cid1].extend(indices2)
                    merged.add(cid2)

        # 병합된 클러스터 제거
        for cid in merged:
            del clusters[cid]

        return clusters

    def _select_representative(self, cluster_leads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """클러스터에서 대표 리드 선택"""
        if len(cluster_leads) == 1:
            return cluster_leads[0]

        # 점수 기반 선택 (priority_score > score > engagement)
        def get_score(lead):
            return (
                lead.get('priority_score', 0) or 0,
                lead.get('score', 0) or 0,
                lead.get('engagement', 0) or lead.get('like_count', 0) or 0
            )

        return max(cluster_leads, key=get_score)

    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return {
            'cache_size': len(self._hash_cache),
            'similarity_threshold': self.similarity_threshold
        }

    def clear_cache(self):
        """캐시 초기화"""
        self._hash_cache.clear()


# 싱글톤 인스턴스
_deduplicator_instance = None


def get_deduplicator(similarity_threshold: float = 0.7) -> CrossPlatformDeduplicator:
    """Deduplicator 싱글톤 인스턴스 반환"""
    global _deduplicator_instance
    if _deduplicator_instance is None:
        _deduplicator_instance = CrossPlatformDeduplicator(similarity_threshold)
    return _deduplicator_instance


def deduplicate_leads(leads: List[Dict[str, Any]], threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    간편 사용을 위한 헬퍼 함수

    Args:
        leads: 원본 리드 목록
        threshold: 유사도 임계값

    Returns:
        중복 제거된 리드 목록 (메타데이터 포함)
    """
    deduplicator = get_deduplicator(threshold)
    deduped = deduplicator.deduplicate(leads)

    # DeduplicatedLead를 Dict로 변환
    results = []
    for item in deduped:
        lead = item.lead.copy()
        lead['_dedup_info'] = {
            'related_platforms': item.related_platforms,
            'duplicate_count': item.duplicate_count,
            'total_reach': item.total_reach,
            'cluster_id': item.cluster_id
        }
        results.append(lead)

    return results
