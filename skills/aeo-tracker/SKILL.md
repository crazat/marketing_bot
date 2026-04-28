---
name: aeo-tracker
description: AEO(Answer Engine Optimization) 가시성 추적. "청주 한의원 추천해줘" 같은 자연어 쿼리에서 LLM이 우리 한의원/경쟁사를 어떻게 답변하는지 측정. 2026 ChatGPT MAU 1,446만 시대의 새 검색 점유율 KPI.
license: Internal
---

# AEO Tracker — LLM 검색 가시성 추적

ChatGPT/Gemini/Cue 등에서 "청주 한의원 추천" 같은 자연어 질의에 우리 한의원이 인용/추천되는지 추적. Cross-User 행동(AI 발견 → 네이버 검증)에서 발견 단계 점유율 측정.

## When to use

- "AEO 측정" / "AI 검색 노출"
- "ChatGPT가 우리 한의원 추천하나"
- "LLM 검색 가시성"
- "Perplexity/Cue/Gemini 노출 점유율"
- "월간 AEO 리포트"
- 명시 X — Pathfinder/Viral 한 사이클 마치고 자연스럽게 측정 권장 (월 1-4회)

## Commands

```bash
# 직전 측정 결과만 보기 (DB 조회, API 호출 없음)
python scripts/aeo_visibility.py --status

# 기본 20개 핵심 키워드 측정 (Gemini Flash Lite + grounding)
python scripts/aeo_visibility.py

# 사용자 지정 키워드만
python scripts/aeo_visibility.py --keywords "청주 한의원 추천,청주 다이어트 한약"

# dry-run (쿼리만 미리보기)
python scripts/aeo_visibility.py --dry-run
```

## Workflow

1. **--status로 직전 결과 확인** — 1주 이내 측정 있으면 사용자에게 "재측정할까요?" 묻기. AEO는 일 단위 큰 변동 적음, 주~월 단위 추적이 적정.

2. **20개 기본 쿼리 또는 사용자 지정 쿼리 측정** — 약 1-2분 소요. Gemini API 비용 ~$0.005/회.

3. **추세 비교** — 직전 측정 대비 노출률 변화 + 신규 노출/탈락 키워드 분석:
   ```sql
   SELECT query_keyword,
          MAX(CASE WHEN id IN (SELECT MAX(id) FROM aeo_visibility GROUP BY query_keyword)
                   THEN our_clinic_mentioned END) latest,
          AVG(our_clinic_mentioned) avg_rate
     FROM aeo_visibility
    WHERE checked_at >= datetime('now','-30 days')
    GROUP BY query_keyword;
   ```

4. **사용자 보고** — 노출률·순위·경쟁사 점유율 비교.

## 보고 템플릿

```markdown
**AEO 가시성 측정 완료** (쿼리 N개, 소요 X분, $Y)

**노출 현황**
- 우리 한의원 노출: M/N 쿼리 (X%)
- 직전 측정 대비: +/-Y%p
- 평균 답변 내 순위: N위

**🔥 노출 우수 쿼리 top 5** (우리가 답변에 등장)
1. "[쿼리]" — 순위 1위 / 경쟁사 N곳 함께 언급
2. ...

**❌ 미노출 쿼리** (개선 기회)
- "[쿼리]" — 경쟁사 [A, B, C]만 언급, 우리 0회
  → 권장 콘텐츠: AEO-friendly FAQ 형식 (40자 이내 핵심 답변 + 명확한 사실 진술)

**경쟁사 점유율 top 3** (LLM이 가장 자주 인용하는 한의원)
1. [한의원명] — N/N 쿼리에서 등장 (X%)

**다음 액션**
- 미노출 쿼리 N건은 콘텐츠 보강 후 1주 후 재측정
- 신규 등장 경쟁사 K곳은 `competitor-watch` 스킬로 별점/단가 추가 모니터링 권장
```

## Guardrails

1. **측정 빈도** — 일 단위 의미 없음. 주~월 단위가 적정. 24시간 내 재측정은 사용자 명시 요청 시만.
2. **Gemini grounding 사용** — Google Search 결과 활용 답변. 비용 약 $0.005/20쿼리. 월 4회 = $0.02/월.
3. **Perplexity 추가 옵션** — 사용자가 명시적으로 "Perplexity로도 측정"이라고 하면 PERPLEXITY_API_KEY 등록 후만 활성. 디폴트는 Gemini만.
4. **자기 한의원 별칭은 business_profile.json::self_exclusion에서 자동 추출** — 별칭 추가 필요하면 사용자에게 안내.
5. **답변 텍스트 5,000자 자르기** — DB 비대화 방지.
6. **AEO 콘텐츠 권장사항** — 측정만으로는 노출 증가 X. FAQ schema + 표 + 명확한 사실 진술 형식 콘텐츠 작성이 인용률 +30~41% (Princeton GEO 2024 논문).

## 출력 길이

- 노출 현황 4-5줄
- 우수/미노출 쿼리 각 top 3-5
- 경쟁사 점유율 top 3
- 다음 액션 1-2개

## 관련 파일/테이블

- `scripts/aeo_visibility.py` (R6)
- `aeo_visibility` 테이블 (query_keyword, llm_provider, response_text, our_clinic_mentioned, competitors_mentioned)
- `config/business_profile.json::self_exclusion` (자기 한의원 별칭)
- `config/targets.json::targets` (경쟁사 명단)
- 의존: `services/ai_client.py::ai_generate` (Gemini Flash Lite)
