"""[R12] browser-use 자율 웹 에이전트 PoC.

목적: Selenium/Camoufox 셀렉터 유지보수 폐기. UI 변경 자동 적응.
       LLM이 click/type/scroll/extract를 자율 결정 → WebVoyager 89.1% 성공률.

용도 후보:
  - 카페 검색 자동화 (cafe_spy 대체 후보)
  - 카카오맵 후기 자동 추출 (R4 보강)
  - Threads 게시물 추출 (R5 보강)
  - 굿닥/하이닥 SPA 검색 결과 자동 추출

설치:
  pip install browser-use playwright
  playwright install chromium

운영자 트리거:
  python scripts/browseruse_poc.py --task "강남 흉터 상담 기준 게시물 추출" --url "https://www.threads.net/search?q=강남흉터상담기준"
  python scripts/browseruse_poc.py --task-file tasks/cafe_extract.txt

비용: GPT-4o-mini ~$0.10/실행, Codex CLI Flash Lite ~$0.01/실행. 단순 작업은 LLM 호출 1-3회.
참조: https://github.com/browser-use/browser-use
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')


async def run_agent(task: str, headless: bool = False) -> str:
    """browser-use Agent is disabled under the Codex CLI-only LLM runtime."""
    return (
        "browser-use PoC is disabled in Codex CLI-only mode. "
        "Use dedicated scraper modules or add a Codex-compatible browser agent adapter first."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True, help='자연어 작업 지시')
    parser.add_argument('--headless', action='store_true', help='UI 안 띄움')
    args = parser.parse_args()

    print(f'=== browser-use PoC ===')
    print(f'task: {args.task}')
    print()

    try:
        result = asyncio.run(run_agent(args.task, headless=args.headless))
    except Exception as e:
        print(f'실행 실패: {e}')
        return 1

    print()
    print('=== 결과 ===')
    print(result)
    print()
    print('다음 단계:')
    print('  - 결과가 만족스러우면 cafe_spy/카카오맵/Threads scraper에 점진 통합')
    print('  - 셀렉터 유지보수 부담 큰 모듈부터 우선 이전 권장')
    return 0


if __name__ == '__main__':
    sys.exit(main())

