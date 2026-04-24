"""viral_service — viral.py 라우터에서 분리한 비즈니스 로직 레이어.

이관 완료:
- record_skip_learning: [D2] 스킵 사유 기록 + 도메인/작성자 감점 누적
- compute_penalty_score: Adaptive filter 감점 계산
- fetch_adaptive_penalties: 반복 skip 대상 조회
- [U3] VerificationCache: 검증 결과 TTL 캐시 (thread-safe)

향후 이관 후보:
- HOT LEAD Telegram 알림
- 댓글 생성 워크플로우
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# [U3] 검증 결과 TTL 캐시 — viral.py에서 이관
class VerificationCache:
    """URL 검증 결과 캐시 (TTL + max_size, thread-safe).

    사용처: viral.py의 verify_url_async → 중복 HTTP 요청 방지.
    """

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000, cleanup_threshold: int = 800):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.cleanup_threshold = cleanup_threshold
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """캐시에서 조회 (만료 시 자동 제거, 없으면 None)."""
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                return None
            if time.time() - entry.get("cached_at", 0) < self.ttl:
                return entry["result"]
            self._cache.pop(url, None)
            return None

    def set(self, url: str, result: Dict[str, Any]) -> None:
        """캐시에 저장 (임계값 초과 시 정리·축소)."""
        now = time.time()
        with self._lock:
            self._cache[url] = {"result": result, "cached_at": now}

            # 만료 정리 (5분 단위로만)
            if now - self._last_cleanup >= 300 and len(self._cache) >= self.cleanup_threshold:
                expired = [
                    k for k, v in self._cache.items()
                    if now - v.get("cached_at", 0) >= self.ttl
                ]
                for k in expired:
                    self._cache.pop(k, None)
                self._last_cleanup = now
                if expired:
                    logger.debug(f"[VerificationCache] 만료 {len(expired)}개 제거, 남은 {len(self._cache)}")

            # 크기 상한 초과 시 가장 오래된 20% 제거
            if len(self._cache) > self.max_size:
                items = sorted(self._cache.items(), key=lambda x: x[1].get("cached_at", 0))
                to_remove = len(self._cache) - int(self.max_size * 0.8)
                for k, _ in items[:to_remove]:
                    self._cache.pop(k, None)
                logger.debug(f"[VerificationCache] 크기 제한으로 {to_remove}개 제거")

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._last_cleanup = 0.0

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# 프로세스 전역 싱글톤 (viral.py에서 import하여 사용)
_verification_cache = VerificationCache()


def record_skip_learning(
    db,
    target_id: str,
    reason_tag: str,
    note: Optional[str] = None,
) -> None:
    """[D2] skip 사유 기록 + 도메인·작성자 감점 누적.

    `db`는 DatabaseManager 싱글톤(기존 패턴). 내부에서 viral_skip_reasons + viral_adaptive_penalties
    두 테이블에 INSERT OR UPDATE.
    """
    try:
        cur = db.cursor
        cur.execute(
            "INSERT INTO viral_skip_reasons(target_id, reason_tag, note) VALUES(?,?,?)",
            (target_id, reason_tag, note),
        )
        cur.execute("SELECT url, author FROM viral_targets WHERE id = ?", (target_id,))
        row = cur.fetchone()
        if not row:
            db.conn.commit()
            return

        url, author = row
        domain = urlparse(url or "").netloc.replace("www.", "")
        now = datetime.now().isoformat()

        if domain:
            cur.execute(
                """
                INSERT INTO viral_adaptive_penalties(key_type, key_value, skip_count, last_updated)
                VALUES('domain', ?, 1, ?)
                ON CONFLICT(key_type, key_value) DO UPDATE
                SET skip_count = skip_count + 1, last_updated = excluded.last_updated
                """,
                (domain, now),
            )
        if author:
            cur.execute(
                """
                INSERT INTO viral_adaptive_penalties(key_type, key_value, skip_count, last_updated)
                VALUES('author', ?, 1, ?)
                ON CONFLICT(key_type, key_value) DO UPDATE
                SET skip_count = skip_count + 1, last_updated = excluded.last_updated
                """,
                (author, now),
            )
        db.conn.commit()
    except Exception as e:
        logger.warning(f"[D2] skip learning failed: {e}")


def compute_penalty_score(skip_count: int, kind: str = "domain") -> int:
    """반복 skip에 따른 감점 점수 계산.

    - domain: skip_count 당 3점 감점, 최대 30점
    - author: skip_count 당 3점 감점, 최대 20점
    """
    per = 3
    cap = 30 if kind == "domain" else 20
    return min(cap, max(0, skip_count) * per)


def fetch_adaptive_penalties(db_path: str, min_skip: int = 3) -> List[Dict[str, Any]]:
    """반복 skip된 도메인·작성자 목록 조회 (감점 대상).

    Repository가 키워드에 한정되므로 adaptive_penalties 테이블은 inline 처리.
    """
    import sqlite3
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT key_type, key_value, skip_count, last_updated
            FROM viral_adaptive_penalties
            WHERE skip_count >= ?
            ORDER BY skip_count DESC
            LIMIT 200
            """,
            (min_skip,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
