---
name: medical-compliance
description: 의료광고법 컴플라이언스 — 한방의료광고심의 가이드북 RAG 인덱스 빌드 + 비급여 단가 일치성 게이트. content_compliance.py가 자동 활용. 2026 신규 규제(AI 의사 광고 금지, 비급여 공개 의무) 대응.
license: Internal
---

# Medical Compliance — 의료광고심의 RAG + 단가 게이트

기존 `services/content_compliance.py`(라운드 2에서 패턴 게이트 + AI 표시 + Vision 게이트 적용)에 두 축 추가:
**(1) 한방의료광고심의 2025 가이드북 PDF → sqlite-vec RAG**
**(2) 비급여 단가 일치성 자동 대조 (심평원 공개 단가 ±10%)**

## When to use

- "가이드북 임베딩" / "의료광고심의 RAG 빌드"
- "단가 게이트 활성화" / "비급여 단가 검증"
- "콘텐츠가 의료광고법 위반인지 확인"
- "심평원 단가와 우리 광고 단가 일치 여부"
- 신규 콘텐츠 작성 후 컴플라이언스 점검 — `screen_korean_comment()` 흐름의 일부로 자동 호출됨

## Decision tree

```
사용자 의도 → 도구 선택
──────────────────────────────────────
"가이드북" / "심의 PDF" / "RAG 빌드"        → build_medical_ad_index.py
"단가 검증" / "verify_price"               → verify_price_consistency() (services/content_compliance.py)
"인덱스 상태"                               → build_medical_ad_index.py --status
"규제 자동 게이트 작동 여부"                → 두 인덱스 + R15 데이터 모두 빌드돼야 함
```

## Commands

```bash
# === R13 가이드북 인덱스 빌드 ===
# 1. PDF 다운로드: https://ad.akom.org/ → 한방의료광고심의 2025 가이드북
# 2. 저장: data/medical_ad_guideline.pdf
python scripts/build_medical_ad_index.py --status                          # 인덱스 상태
python scripts/build_medical_ad_index.py                                   # 빌드
python scripts/build_medical_ad_index.py --pdf custom.pdf --rebuild        # 다른 PDF로 재빌드

# === R14 단가 게이트 (R15 선행 필요) ===
# 1. 사전: 경쟁사 단가 수집
python scripts/hira_oasis_harvester.py --hira-hospitals
python scripts/competitor_pricing_collector.py
# 2. 콘텐츠 검증 (Python 직접 호출)
python -c "
from services.content_compliance import verify_price_consistency
result = verify_price_consistency('우리 추나치료 30,000원입니다')
print(result)
"
```

## Workflow

1. **인덱스 상태 점검** — 둘 다 안 빌드돼있으면 사용자에게 안내:
   ```
   - medical_ad_chunks: build_medical_ad_index.py
   - hira_nonpay_items: hira_oasis_harvester.py + competitor_pricing_collector.py
   ```
2. **PDF 위치 확인** — `data/medical_ad_guideline.pdf` 없으면 `https://ad.akom.org/` 안내 + 운영자 다운로드 대기.
3. **빌드 실행** — BGE-M3 임베딩 (568MB 모델 + 임베딩 시간), 약 2-5분.
4. **자동 게이트 작동 검증** — 빌드 후 샘플 콘텐츠로 `verify_price_consistency()` + `search_guideline()` 호출 결과 보여주기.
5. **사용자 보고**

## 보고 템플릿

```markdown
**의료광고법 컴플라이언스 인프라 빌드 완료**

**RAG 가이드북 인덱스**
- 청크 수: N개 (한방의료광고심의 2025 가이드북)
- 섹션 분포: 금지 표현 N / 심의 절차 N / 기타 N

**단가 일치성 데이터**
- hira_nonpay_items: N건 (M개 한의원, K개 항목)
- 마지막 갱신: YYYY-MM-DD

**자동 게이트 작동 흐름**
- ✅ `screen_korean_comment()` 호출 시 자동:
  - regex 패턴 게이트 (라운드 2 C1·C2·C3)
  - 가이드북 RAG 검색 (R13) — 청구 매칭 시 위반 의심 알림
  - 단가 일치성 (R14) — 콘텐츠 내 가격 ±10% 검증
- ✅ Vision 의료 이미지 게이트 (라운드 2 C3) 동시 작동

**테스트 결과** (샘플 "우리 추나치료 30,000원입니다")
- 가이드북 매칭: [관련 청크 1개, 점수 0.78]
- 단가 비교: 추나치료 청주 평균 50,000 / 우리 30,000 (편차 -40%)
- verdict: ⚠️ fail (편차 ±10% 초과)

**다음 액션**
- viral-comment-drafter / 블로그 작성 흐름이 자동 활용
- 가이드북 PDF 갱신 시 `--rebuild`로 재빌드
- 단가 데이터는 월 1회 `competitor-watch` 갱신 권장
```

## Guardrails

1. **PDF 출처 검증** — 한방의료광고심의 공식(https://ad.akom.org/)에서만 다운로드. 비공식 PDF 사용 금지.
2. **PDF 임베딩 1회만** — 가이드북 갱신 시 `--rebuild` 필요. 같은 PDF로 재빌드는 시간 낭비.
3. **단가 게이트 false positive 주의** — 콘텐츠 내 "원래 50,000원이었는데 지금은..." 같은 비교 표현은 verify_price가 첫 가격에 매칭 시도. 결과 verdict='warn' 시 사람 검토 권장.
4. **인덱스 미빌드 시 silent 폴백** — `is_guideline_indexed()`가 False면 RAG 게이트만 비활성화, 다른 게이트는 정상 작동. 운영 중단 X.
5. **2025 가이드북 → 2026 갱신 시점** — 매년 갱신. 통상 4-5월 신규 발간. 알림 받으면 즉시 재빌드 권장.
6. **단가 데이터 신선도** — 비급여 공개 마감 2026-6-12. 그 전엔 부분 적재. `last_updated_at` 함께 보고.
7. **Vision 게이트와 별개** — 이미지 의료광고법 검사는 `services/content_compliance.py::screen_medical_image()` (라운드 2 C3). 본 스킬은 텍스트 영역만 다룸.

## 출력 길이

- 인덱스 현황 5-6줄
- 자동 게이트 흐름 5-6줄
- 테스트 결과 샘플 1개
- 다음 액션 2-3개

## 관련 파일/테이블

- `scripts/build_medical_ad_index.py` (R13 빌더)
- `services/rag/medical_ad_search.py` (R13 검색)
- `services/content_compliance.py::verify_price_consistency()` (R14 게이트)
- `services/content_compliance.py::screen_korean_comment()` (전체 통합 진입점)
- `medical_ad_chunks` + `medical_ad_vec` 테이블 (sqlite-vec)
- `hira_nonpay_items` 테이블 (R15 적재)
- 의존: `sentence-transformers` (BGE-M3), `sqlite-vec`, `pypdf`
- 후속 스킬: `competitor-watch` (단가 데이터 갱신), `scan-competitors` (리뷰 컴플라이언스)
