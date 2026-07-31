import os

import pytest


os.environ.setdefault("MARKETING_BOT_CLINIC_PROFILE", "gyulim_cheongju")


@pytest.fixture(autouse=True)
def _semantic_discovery_off_by_default(monkeypatch):
    """의미기반 발견(semantic discovery)은 opt-in(기본 off)이고, 테스트는 그 기본
    계약(콜로퀴얼 변형 없음·매처 no-op)을 검증한다. 프로덕션에서 .env 가
    ``MARKETING_BOT_SEMANTIC_DISCOVERY=1`` 로 켜져 있어도 테스트 프로세스는 격리해
    회귀를 막는다. ON 동작을 검증하는 테스트는 각자 ``monkeypatch.setenv`` 로 켠다
    (function-scope 본문이 이 autouse 셋업보다 뒤에 실행되어 우선한다)."""
    monkeypatch.delenv("MARKETING_BOT_SEMANTIC_DISCOVERY", raising=False)
