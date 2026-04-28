"""[R11] Anthropic + OpenAI Batch API wrapper — 옵션 stub.

⚠️ 디폴트 정책: 이 모듈은 활성화하지 말 것. Gemini 단일 정책 유지.
   - Gemini가 이미 batch (50%) + implicit caching (75-90%) = 87.5% 절감
   - Gemini 3.1 Flash Lite Preview는 한국어 자연스러움 더 좋고 단가도 더 쌈
   - Anthropic/OpenAI 추가 시 운영 복잡도 ↑, 절감 차이는 월 $5 미만

이 wrapper는 향후 사용자가 명시적으로 "Anthropic vs Gemini A/B 검증" 같은 작업 요청 시에만 활성.
일상 분류·생성은 services/ai_client.py의 ai_generate_batch / ai_generate / ai_generate_korean 사용.

비용 비교 (참고):
  - Gemini Flash Lite: $0.10/$0.40 + caching 75-90% + batch 50% (현재 사용 중)
  - Anthropic Sonnet:  $3/$15    + cache 90%    + batch 50%
  - OpenAI gpt-4o-mini:$0.15/$0.60 + cache 50%   + batch 50%

API 키 (선택, 없으면 자동 비활성):
  ANTHROPIC_API_KEY  — A/B 검증용으로만 등록 (디폴트 운영에 불필요)
  OPENAI_API_KEY     — A/B 검증용으로만 등록

사용 흐름:
  from services.multi_provider_batch import submit_anthropic_batch, get_anthropic_batch_results
  job = submit_anthropic_batch(requests, model='claude-sonnet-4-6')
  # 1~24시간 후
  results = get_anthropic_batch_results(job_id)

Anthropic Message Batches API: https://docs.anthropic.com/en/api/creating-message-batches
OpenAI Batch API:            https://platform.openai.com/docs/guides/batch
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _anthropic_client():
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic 패키지 미설치. pip install anthropic 후 재시도.")
        return None
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        logger.info("ANTHROPIC_API_KEY 없음. Anthropic batch 비활성.")
        return None
    return anthropic.Anthropic(api_key=key)


def _openai_client():
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai 패키지 미설치. pip install openai 후 재시도.")
        return None
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        logger.info("OPENAI_API_KEY 없음. OpenAI batch 비활성.")
        return None
    return OpenAI(api_key=key)


# ============================================================
# Anthropic
# ============================================================

def submit_anthropic_batch(
    requests: list[dict],
    model: str = 'claude-sonnet-4-6',
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """Anthropic Message Batches 제출.

    Args:
        requests: list of dicts with 'custom_id' and 'prompt'.
        model: claude-sonnet-4-6 / claude-haiku-4-5 / claude-opus-4-7.
        max_tokens: 응답 토큰 제한.
        system_prompt: prompt cache 활용 — 1024+ tokens 권장.

    Returns:
        batch_id (None=실패).
    """
    client = _anthropic_client()
    if client is None:
        return None

    formatted = []
    for r in requests:
        msg = {
            'custom_id': r['custom_id'],
            'params': {
                'model': model,
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': r['prompt']}],
            },
        }
        if system_prompt:
            # cache_control로 system 캐싱 (90% 절감)
            msg['params']['system'] = [{
                'type': 'text', 'text': system_prompt,
                'cache_control': {'type': 'ephemeral'},
            }]
        formatted.append(msg)

    try:
        batch = client.messages.batches.create(requests=formatted)
        logger.info(f"Anthropic batch 제출: id={batch.id}, count={len(formatted)}")
        return batch.id
    except Exception as e:
        logger.error(f"Anthropic batch 제출 실패: {e}")
        return None


def get_anthropic_batch_status(batch_id: str) -> Optional[str]:
    client = _anthropic_client()
    if client is None:
        return None
    try:
        b = client.messages.batches.retrieve(batch_id)
        return b.processing_status  # in_progress / ended / canceled / errored
    except Exception as e:
        logger.error(f"Anthropic batch 상태 조회 실패: {e}")
        return None


def get_anthropic_batch_results(batch_id: str) -> Optional[list[dict]]:
    """완료된 batch 결과 회수. processing_status=='ended' 일 때만."""
    client = _anthropic_client()
    if client is None:
        return None
    try:
        results = []
        for entry in client.messages.batches.results(batch_id):
            results.append({
                'custom_id': entry.custom_id,
                'text': entry.result.message.content[0].text if entry.result.type == 'succeeded' else '',
                'status': entry.result.type,
            })
        return results
    except Exception as e:
        logger.error(f"Anthropic batch 결과 회수 실패: {e}")
        return None


# ============================================================
# OpenAI
# ============================================================

def submit_openai_batch(
    requests: list[dict],
    model: str = 'gpt-4o-mini',
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """OpenAI Batch API 제출. 24시간 내 완료, 50% 할인."""
    client = _openai_client()
    if client is None:
        return None

    # 1. JSONL 파일 생성
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    try:
        for r in requests:
            messages = []
            if system_prompt:
                messages.append({'role': 'system', 'content': system_prompt})
            messages.append({'role': 'user', 'content': r['prompt']})
            line = {
                'custom_id': r['custom_id'],
                'method': 'POST',
                'url': '/v1/chat/completions',
                'body': {
                    'model': model,
                    'messages': messages,
                    'max_tokens': max_tokens,
                },
            }
            tmp.write(json.dumps(line, ensure_ascii=False) + '\n')
        tmp.close()

        # 2. 파일 업로드
        with open(tmp.name, 'rb') as f:
            uploaded = client.files.create(file=f, purpose='batch')

        # 3. batch 제출
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint='/v1/chat/completions',
            completion_window='24h',
        )
        logger.info(f"OpenAI batch 제출: id={batch.id}")
        return batch.id
    except Exception as e:
        logger.error(f"OpenAI batch 제출 실패: {e}")
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def get_openai_batch_status(batch_id: str) -> Optional[str]:
    client = _openai_client()
    if client is None:
        return None
    try:
        b = client.batches.retrieve(batch_id)
        return b.status  # validating / in_progress / completed / failed
    except Exception as e:
        logger.error(f"OpenAI batch 상태 조회 실패: {e}")
        return None


def get_openai_batch_results(batch_id: str) -> Optional[list[dict]]:
    client = _openai_client()
    if client is None:
        return None
    try:
        b = client.batches.retrieve(batch_id)
        if b.status != 'completed' or not b.output_file_id:
            return None
        content = client.files.content(b.output_file_id).text
        results = []
        for line in content.strip().split('\n'):
            entry = json.loads(line)
            choice = entry.get('response', {}).get('body', {}).get('choices', [{}])[0]
            results.append({
                'custom_id': entry['custom_id'],
                'text': choice.get('message', {}).get('content', ''),
                'status': 'succeeded' if not entry.get('error') else 'failed',
            })
        return results
    except Exception as e:
        logger.error(f"OpenAI batch 결과 회수 실패: {e}")
        return None


__all__ = [
    'submit_anthropic_batch',
    'get_anthropic_batch_status',
    'get_anthropic_batch_results',
    'submit_openai_batch',
    'get_openai_batch_status',
    'get_openai_batch_results',
]
