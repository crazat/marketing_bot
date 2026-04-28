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
  python scripts/browseruse_poc.py --task "청주 한의원 추천" --url "https://www.threads.net/search?q=청주한의원"
  python scripts/browseruse_poc.py --task-file tasks/cafe_extract.txt

비용: GPT-4o-mini ~$0.10/실행, Gemini Flash Lite ~$0.01/실행. 단순 작업은 LLM 호출 1-3회.
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
    """browser-use Agent로 task 실행, 결과 텍스트 반환."""
    try:
        from browser_use import Agent, Browser, BrowserConfig
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        return (
            f'browser-use 의존성 미설치: {e}\n'
            'pip install browser-use langchain-google-genai playwright\n'
            'playwright install chromium'
        )

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        # secrets에서 폴백
        try:
            with open(os.path.join(ROOT_DIR, 'config', 'secrets.json'), 'r', encoding='utf-8') as f:
                api_key = json.load(f).get('GEMINI_API_KEY')
        except Exception:
            pass
    if not api_key:
        return 'GEMINI_API_KEY 없음. browser-use 실행 불가.'

    llm = ChatGoogleGenerativeAI(
        model='gemini-2.5-flash-lite',
        google_api_key=api_key,
        temperature=0.2,
    )

    browser = Browser(config=BrowserConfig(headless=headless))
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=4,
    )

    result = await agent.run(max_steps=15)
    await browser.close()

    return str(result)


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
