---
name: content-quality
description: 콘텐츠 품질 강화 — A/B chi-square 검정, 카니발리제이션 검출, BGE-M3 갭 분석, Schema.org JSON-LD 생성, 검색의도 7-tier 재분류. 게시 자동화 X (측정·발견·draft만).
license: Internal
---

# Content Quality — 5개 모듈 콘텐츠 품질 강화

자사 콘텐츠가 실제로 검색·전환에 기여하는지 측정·발견하는 도구 모음. **자동 게시·자동 댓글 일체 없음**(CLAUDE.md 정책 준수).

## When to use

- "A/B 결과" / "p-value" / "유의성" / "이긴 변형"
- "카니발리제이션" / "같은 키워드 우리 글 두 개"
- "갭 분석" / "경쟁사가 다루는데 우리가 안 다룬"
- "Schema.org" / "구조화 데이터" / "FAQ rich result" / "JSON-LD"
- "의도 재분류" / "콘텐츠 검색의도" / "search_intent"

## Decision tree

```
사용자 의도 → 도구 선택
─────────────────────────────────────────────────
"A/B 결과" / "유의" / "winning"           → ab_test_stats.summarize_ab_test
"카니발 후보" / "같은 검색어 두 URL"      → scripts/content_cannibalization.py
"우리가 안 다룬 주제" / "갭"              → scripts/content_gap_analyzer.py
"FAQ rich result" / "구조화"              → scripts/generate_site_schema.py
"의도 분류" / "intent 분포"               → scripts/reclassify_content_intent.py
```

## Commands

```bash
# === 1. A/B chi-square ===
python -c "
from services.ab_test_stats import summarize_ab_test
import json; print(json.dumps(summarize_ab_test(test_id=1), ensure_ascii=False, indent=2))
"

# === 2. 카니발리제이션 ===
python scripts/content_cannibalization.py --status
python scripts/content_cannibalization.py --days 28 --min-clicks 5
python scripts/content_cannibalization.py --dry-run

# === 3. 콘텐츠 갭 (BGE-M3, 첫 실행 시 모델 568MB 다운로드) ===
python scripts/content_gap_analyzer.py --status
python scripts/content_gap_analyzer.py --top 30
python scripts/content_gap_analyzer.py --dry-run --no-seed

# === 4. Schema.org JSON-LD 생성 ===
python scripts/generate_site_schema.py --status
python scripts/generate_site_schema.py --max-faq 30
# 출력: data/generated_schema/medical_business.jsonld, faq_page.jsonld

# === 5. 검색의도 7-tier 재분류 ===
python scripts/reclassify_content_intent.py --status
python scripts/reclassify_content_intent.py --limit 50
python scripts/reclassify_content_intent.py --force --limit 100
```

## Workflow

1. **상태 점검** — 사용자 의도에 맞는 `--status` 먼저. 의존 테이블/파일 누락 시 안내 후 종료.
2. **dry-run 우선 권유** — 처음 실행이면 `--dry-run`으로 결과 미리보기.
3. **실 실행** — 사용자 승인 후 적재 모드.
4. **DB 직접 검증** — `cannibalization_findings`, `content_gaps`, `qa_repository.search_intent` 등 결과 SQL로 카운트 재확인.
5. **인사이트 보고** — 숫자 + 원인 추정 + 다음 액션 1~3개.

## 보고 템플릿

```markdown
**콘텐츠 품질 점검 결과**

**[1] A/B 검정** (실험 #N "이름")
- 변형 A 전환율: X.X% (CI 95%: a~b)
- 변형 B 전환율: Y.Y% (CI 95%: c~d)
- 결론: 유의함(p=0.0XX) / 유의 미달(N건 추가 필요)

**[2] 카니발리제이션** (최근 28일)
- 후보 N건 (high N / medium N / low N)
- top 3: 검색어 — 경쟁 URL 2개 — 점유율 X%/Y%

**[3] 콘텐츠 갭**
- 자사 corpus M개 vs 경쟁사 K개 → 갭 N건
- top 3: 경쟁사 주제 — 가장 가까운 자사 URL — 유사도 0.XX
- 제안 시드: ["키워드1", ...]

**[4] Schema.org**
- medical_business.jsonld: 검증 통과 / 권장 N건
- faq_page.jsonld: Q&A N건 적재

**[5] 의도 분포** (qa_repository / viral_targets)
- informational X% / commercial Y% / transactional Z% / ...

**다음 액션**
1. 카니발 high 후보 K개 — 정전(canonical) 또는 병합 검토
2. 갭 top 3 시드를 pathfinder 키워드 풀에 추가
3. JSON-LD 파일을 사이트 <script type="application/ld+json"> 삽입
```

## Guardrails

1. **Gemini-only** — `services.ai_client.ai_generate*`만 사용. Anthropic/OpenAI 키 추가 X.
2. **GSC 의존** — 카니발리제이션은 `inbound_search_queries` 테이블 필요. 미존재 시 graceful skip + 안내.
3. **자기 한의원 필터** — 갭/의도 재분류는 `business_profile.json::self_exclusion`을 통해 자기 한의원 콘텐츠만 자사로 인정.
4. **자동 게시 금지** — Schema.org JSON-LD는 파일로만 출력. 사이트 삽입은 운영자 수동.
5. **DB 직접 cp 금지** — 결과 적재는 INSERT만. DB 복사 필요 시 `scripts/safe_db_copy.sh` 또는 `db_backup.py`.
6. **BGE-M3 첫 실행** — 568MB 모델 다운로드. CPU에서 corpus 1000건 ~30~60초 소요. 중간 종료 자제.
7. **chi-square 최소 샘플** — 각 변형 5건 미만이면 검정 미수행 + 안내. p<0.05 도달 전엔 "유의 미달" 명시.
8. **dry-run 권장** — 첫 실행이면 `--dry-run`으로 적재 전 결과 확인.

## 출력 길이

- 후보·갭 10건 이내면 모두, 초과면 top 5 + "외 N개"
- A/B 결과는 한 실험당 4~5줄
- Schema 검증 issues 5건 이내면 모두, 초과면 카테고리별 카운트
- 전체 보고 30~60줄 권장

## 관련 파일/테이블

**파일**
- `services/ab_test_stats.py` (chi-square 검정)
- `services/schema_generator.py` (JSON-LD 생성)
- `scripts/content_cannibalization.py`
- `scripts/content_gap_analyzer.py`
- `scripts/reclassify_content_intent.py`
- `scripts/generate_site_schema.py`

**테이블**
- `cannibalization_findings` (신규)
- `content_gaps` (신규)
- `qa_repository.search_intent` (컬럼 추가)
- `viral_targets.search_intent` (컬럼 추가)
- 활용: `ab_experiments`, `ab_variants`, `ab_assignments`, `competitor_blog_activity`, `inbound_search_queries`(외부 의존)

**의존성**
- `scipy` (chi-square)
- `sentence-transformers` + BGE-M3 (갭 분석, qa_search.py와 동일 모델)
- `services.ai_client.ai_generate_json` (시드 제안, 의도 분류)

**연계 스킬**
- `scan-pathfinder` (갭에서 발견된 시드를 키워드 풀에 추가)
- `medical-compliance` (의료광고법 게이트는 별개)
- `viral-comment-drafter` (의도 분포로 댓글 톤 보정)
