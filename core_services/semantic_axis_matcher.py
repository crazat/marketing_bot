"""의미기반(semantic) 진료축 매처 — 어휘 일치가 놓치는 구어/패러프레이즈 환자글 회수.

바이럴 헌터의 발견·매칭은 100% 어휘(literal token) 기반이라 환자가 임상어 없이 구어로
쓴 글("얼굴 짝짝이"=안면비대칭, "팬자국/구덩이"=흉터)을 통째로 놓친다. 이 모듈은 기존
RAG 스택과 동일한 로컬 임베딩(BGE-M3, sentence-transformers)을 재사용해(새 제공자 추가
없음) 글과 진료축 기준어 사이의 의미 유사도를 계산, 어휘로는 mismatch 인 글을 의미적으로
구제하는 데 쓴다.

설계 원칙:
- **Fail-soft / opt-in**: 모델이 없거나 `MARKETING_BOT_SEMANTIC_DISCOVERY` 가 꺼져 있으면
  `available()` 이 False → 호출부는 완전 no-op (기존 어휘 동작 그대로, 회귀 0).
- **주입 가능**: `embed_fn` 을 주입하면(테스트) 모델 없이도 결정적으로 동작한다.
- **순수 cosine**: numpy 없이도 list 벡터를 처리(테스트 fake 벡터 호환).
- 단일 LLM/임베딩 정책 준수 — BGE-M3 는 로컬, 외부 제공자 추가 아님.
"""
from __future__ import annotations

import logging
import math
import os
import threading
from typing import Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.62
_ENABLE_ENV = "MARKETING_BOT_SEMANTIC_DISCOVERY"
_THRESHOLD_ENV = "MARKETING_BOT_SEMANTIC_AXIS_THRESHOLD"
_MODEL_ENV = "MARKETING_BOT_EMBED_MODEL"


def semantic_discovery_enabled() -> bool:
    """의미기반 발견 기능군(구어 쿼리 확장 + 의미 매칭) opt-in 게이트.

    기본 꺼짐 → 신규 동작이 없어 회귀 0. `MARKETING_BOT_SEMANTIC_DISCOVERY=1` 로 활성화.
    """
    return str(os.environ.get(_ENABLE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        x = float(x)
        y = float(y)
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class SemanticAxisMatcher:
    """글 ↔ 진료축 기준어의 의미 유사도. 모델/주입 없으면 비활성(no-op)."""

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], Optional[Sequence[float]]]] = None,
        *,
        threshold: Optional[float] = None,
    ) -> None:
        self._embed_fn = embed_fn
        self._injected = embed_fn is not None
        self._load_attempted = False
        self._lock = threading.Lock()
        self._ref_cache: Dict[str, Optional[List[float]]] = {}
        if threshold is not None:
            self._threshold = float(threshold)
        else:
            try:
                self._threshold = float(os.environ.get(_THRESHOLD_ENV, _DEFAULT_THRESHOLD))
            except (TypeError, ValueError):
                self._threshold = _DEFAULT_THRESHOLD

    @property
    def threshold(self) -> float:
        return self._threshold

    @staticmethod
    def _env_enabled() -> bool:
        return semantic_discovery_enabled()

    def _resolve_embed_fn(self) -> Optional[Callable[[str], Optional[Sequence[float]]]]:
        if self._embed_fn is not None:
            return self._embed_fn
        if not self._env_enabled():
            return None  # opt-in 게이트 — 기본 비활성
        if self._load_attempted:
            return self._embed_fn
        with self._lock:
            if self._load_attempted:
                return self._embed_fn
            self._load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                model_id = os.environ.get(_MODEL_ENV, "BAAI/bge-m3")
                model = SentenceTransformer(model_id)

                def _encode(text: str):
                    return model.encode(text, normalize_embeddings=True)

                self._embed_fn = _encode
            except Exception as exc:  # 모델/의존성 부재 → 영구 no-op
                logger.warning(f"semantic axis matcher 비활성(임베딩 모델 로드 실패): {exc}")
                self._embed_fn = None
        return self._embed_fn

    def available(self) -> bool:
        return self._resolve_embed_fn() is not None

    def _embed(self, text: str) -> Optional[List[float]]:
        fn = self._resolve_embed_fn()
        if fn is None:
            return None
        text = (text or "").strip()
        if not text:
            return None
        try:
            vec = fn(text)
        except Exception as exc:
            logger.debug(f"semantic embed 실패: {exc}")
            return None
        if vec is None:
            return None
        try:
            return [float(x) for x in vec]
        except TypeError:
            return None

    def _reference_vector(self, ref_terms: Sequence[str], ref_key: str) -> Optional[List[float]]:
        if ref_key in self._ref_cache:
            return self._ref_cache[ref_key]
        terms = [str(t).strip() for t in (ref_terms or ()) if str(t).strip()]
        vec = self._embed(" ".join(terms)) if terms else None
        self._ref_cache[ref_key] = vec
        return vec

    def similarity(
        self,
        text: str,
        ref_terms: Sequence[str],
        *,
        ref_key: str,
    ) -> Optional[float]:
        """글과 진료축 기준어의 cosine 유사도. 비활성/실패 시 None."""
        tv = self._embed(text)
        if tv is None:
            return None
        rv = self._reference_vector(ref_terms, ref_key)
        if rv is None:
            return None
        return _cosine(tv, rv)

    def is_on_axis(self, text: str, ref_terms: Sequence[str], *, ref_key: str) -> bool:
        sim = self.similarity(text, ref_terms, ref_key=ref_key)
        if sim is None:
            return False
        return sim >= self._threshold
