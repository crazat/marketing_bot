---
name: viral-comment-drafter
description: 청주 규림한의원 바이럴 타겟(YouTube/지식인/카페/블로그) lead를 입력받아 BGE-M3 RAG로 Q&A 매칭 → 의료광고법 게이트 통과 댓글 초안 생성 → URL 검증 결과 반환. 자동 게시 절대 금지, 모든 결과는 pending_approvals 테이블에 적재 후 Telegram HITL 승인 워크플로우.
license: Internal
---

# Viral Comment Drafter

Lead 1건의 댓글 초안을 만들고 사람 승인 큐에 넣는 5-tool 결정 루프.

## When to use

다음 상황에서 호출:
- ViralHunter에서 신규 lead가 발견됐을 때 (cron / scan_runs 트리거)
- Lead Manager에서 사람이 단일 lead "댓글 초안 생성" 클릭
- 일괄 처리 모드 (점심시간 등 — 30개 lead를 한 번에 큐에 적재)

## What it does (Workflow)

```
[lead_id]
    ↓
1. _fetch_lead(lead_id) — viral_targets에서 lead 정보 로드
2. check_dup_history(author, url) — 30일 내 중복 컨택 차단
3. search_qa_repository(lead_text) — BGE-M3 + bge-reranker-v2-m3
4. ┌─────────────────────────────────────────┐
   │ for attempt in 1..3:                     │
   │   draft_korean_comment(text, qa, fb?)    │
   │   critique_compliance(draft)             │
   │   if score >= 0.75 and compliance: break │
   │   feedback = critique.issues             │
   │ else: escalate                           │
   └─────────────────────────────────────────┘
5. verify_destination_url(url, platform) — Selenium async
6. append_ai_disclosure(final) — AI 기본법 푸터
7. _enqueue_approval(lead_id, draft, qa_ids, critique, url_check)
8. notify_pending_approval(approval_id, ...) — Telegram 4-button card
```

## Tools (5)

| Tool | File | Purpose |
|---|---|---|
| `search_qa_repository` | services/rag/qa_search.py | BGE-M3 dense + FTS5 BM25 + RRF + reranker |
| `draft_korean_comment` | services/agent_runtime.py | ai_generate_korean wrap (compliance OFF, structured prompt) |
| `critique_compliance` | services/agent_runtime.py | regex (의료광고법) + LLM-as-judge (자연스러움/톤) → 3축 score |
| `verify_destination_url` | services/comment_verifier.py | URL alive/captcha/login_required |
| `check_dup_history` | services/agent_runtime.py | contact_history + viral_targets 중복 검사 |

## Guardrails (절대 위반 금지)

1. **자동 게시 금지** — `enqueue_for_hitl()` 사용. 절대 직접 POST 금지.
2. **의료법 위반 콘텐츠 게시 금지** — `critique_compliance.compliance.passed=False`이면 무조건 escalate.
3. **자기 한의원 블로그 차단** — `business_profile.json::self_exclusion`의 `blog_authors`/`url_patterns`/`title_keywords` 매칭 시 즉시 skip.
4. **AI 의료진 추천 표현 금지** — 2026-04-23 개정법으로 전면 금지.
5. **30분 만료** — pending_approvals expires_at 지나면 status='expired', 알림 자동 retry.
6. **AI 고지 푸터 의무** — 모든 최종 댓글에 "본 콘텐츠는 AI 보조로 작성되었습니다" 자동 첨부.

## Files

- `services/agent_runtime.py` — 메인 process_lead() 함수
- `services/telegram_approval.py` — HITL 알림
- `routers/telegram_callback.py` — 인바운드 콜백 webhook
- `services/content_compliance.py` — 의료광고법 패턴 + screen_korean_comment()
- `services/rag/qa_search.py` — BGE-M3 RAG

## Inputs / Outputs

```python
# Input
lead_id: int   # viral_targets.id (TEXT지만 int 캐스트 가능)

# Output
{
  "status": "pending_approval" | "abort" | "escalate",
  "approval_id": int (status가 pending_approval일 때),
  "draft": str,
  "critique_score": float,
  "qa_match_ids": list[int],
  "reason": str (abort/escalate일 때)
}
```

## Cost target

- per lead < $0.005 (Gemini 2.5 Flash Lite + cached system_prompt)
- per lead 사람 시간 < 15초 (Telegram 4-button 1탭)

## Success metrics

| Metric | Target (90일) |
|---|---|
| Compliance violation 사후 발견 | 0건 |
| Q&A match hit rate | > 70% |
| Approval rate (사람 승인) | > 60% |
| Average lead → 게시 lead time | < 30분 |
