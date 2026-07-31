"""바이럴 댓글 'AI 보조 고지 푸터' 비부착 + 1인칭 경험담 유지 회귀 테스트.

운영 결정(2026-06-19): 바이럴 댓글은 '실제 다녀온 환자 후기' 톤을 깨지 않도록
- AI 보조 고지 푸터("※ 본 콘텐츠는 AI 보조로 작성되었습니다.")를 붙이지 않는다.
- 컴플라이언스 retry 시 1인칭 치료 경험 표현 제거를 지시하지 않는다.
그 외 한국어 콘텐츠(blog 등)는 기존대로 고지 푸터를 유지한다.
"""
import services.ai_client as ai_client


class _FakeResult:
    def __init__(self, text):
        self.text = text


class _FakeCodex:
    def __init__(self):
        self.last_prompt = None

    def generate_text(self, prompt, **kwargs):
        self.last_prompt = prompt
        return _FakeResult("청주 성안길 규림한의원 다녀왔는데 상담이 꼼꼼했어요")

    def record_codex_call(self, *args, **kwargs):
        pass


def _patch(monkeypatch, screen_passed=True):
    fake = _FakeCodex()
    monkeypatch.setattr(ai_client, "_require_codex", lambda: fake)
    monkeypatch.setattr(
        ai_client,
        "_screen_korean_text",
        lambda text, prompt, **kw: {"passed": screen_passed, "final_text": text, "violations": []},
    )
    return fake


def test_viral_comment_omits_ai_disclosure_footer(monkeypatch):
    _patch(monkeypatch)
    out = ai_client.ai_generate_korean("댓글 작성", task="viral_comment")
    assert "AI 보조로 작성" not in out          # 환자 후기 톤 유지 — 고지 푸터 없음
    assert "규림한의원 다녀왔는데" in out          # 1인칭 경험담 본문은 그대로


def test_non_viral_korean_keeps_ai_disclosure_footer(monkeypatch):
    _patch(monkeypatch)
    out = ai_client.ai_generate_korean("블로그 문단", task="korean_content")
    assert "AI 보조로 작성" in out               # 그 외 콘텐츠는 기존대로 고지 유지


def test_viral_comment_retry_does_not_strip_first_person(monkeypatch):
    # 첫 스크린 실패 → retry 경로 진입. retry 프롬프트에 1인칭 제거 지시가 없어야 한다.
    fake = _FakeCodex()
    monkeypatch.setattr(ai_client, "_require_codex", lambda: fake)
    calls = {"n": 0}

    def screen(text, prompt, **kw):
        calls["n"] += 1
        return {"passed": calls["n"] > 1, "final_text": text, "violations": []}

    monkeypatch.setattr(ai_client, "_screen_korean_text", screen)
    ai_client.ai_generate_korean("댓글 작성", task="viral_comment")
    assert "Required revision" in (fake.last_prompt or "")            # retry 발생
    assert "Remove first-person treatment experience" not in (fake.last_prompt or "")
    # 경성 의료광고법 가드는 그대로 유지된다.
    assert "Remove guaranteed outcomes" in (fake.last_prompt or "")


def test_non_viral_retry_still_strips_first_person(monkeypatch):
    fake = _FakeCodex()
    monkeypatch.setattr(ai_client, "_require_codex", lambda: fake)
    calls = {"n": 0}

    def screen(text, prompt, **kw):
        calls["n"] += 1
        return {"passed": calls["n"] > 1, "final_text": text, "violations": []}

    monkeypatch.setattr(ai_client, "_screen_korean_text", screen)
    ai_client.ai_generate_korean("블로그 문단", task="korean_content")
    assert "Remove first-person treatment experience" in (fake.last_prompt or "")
