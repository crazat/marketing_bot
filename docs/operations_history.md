# Pathfinder · Viral Hunter 운영 이력 요약

> 상세 JSON 감사 리포트는 `reports/`, 세부 대화 메모는 사용자별 Claude memory에 보관한다.
> 여기에는 현재 운영 판단에 다시 쓰일 수 있는 변화만 압축 기록한다.

> 현재 작업의 안정적인 규칙은 [CLAUDE.md](../CLAUDE.md)와
> [운영 계약](OPERATING_CONTRACTS.md)을 기준으로 한다. 아래 내용은 이력·결과 요약이다.

## 2026-04 ~ 06 초반: 기반 정비

- AI 호출을 `ai_client.py` 단일 진입점으로 통합하고, Camoufox·RAG·관측성 기반을 구축했다.
- 플레이스 스크래퍼, Settings/Viral UI, API 클라이언트를 분리했다.
- 바이럴 후보의 카테고리·광고·지역·중복·시점 게이트를 단계적으로 정비했다.

## 2026-06-20 ~ 07-05: 발견 품질과 피드백 루프

- 1인칭 바이럴 경험담 정책을 프롬프트·컴플라이언스·생성 게이트에 일관되게 적용했다.
- semantic discovery를 프로덕션 opt-in으로 활성화했고, 흉터/안면비대칭 시그니처 축에
  backlog rescue, Q&A 시딩, 자체 콘텐츠 브리프, SLA를 추가했다.
- Pathfinder → Viral handoff audit에 seed intent, platform surface, route, treatment signal,
  execution readiness, freshness/rediscovery 지표를 추가했다.
- query variant와 source seed에 대해 scale/repair/retire feedback을 계산하고 다음 스캔의
  검색 예산과 seed 선택에 자동 반영하도록 했다.
- metric coverage가 부족한 과거 스캔에는 Pathfinder lineage·quality metric backfill을 적용했다.
- manual review 위험 글은 자동 pending 큐에서 분리했고, stale-window·광고·삭제 글이
  auto rescue되지 않도록 계약을 강화했다.

## 2026-07-07 ~ 07-11: 세부의도·rescue·실행 안전성

- seed quota와 AI category floor 안에서 치료 세부의도 다양성을 보장했다.
- enrichment에서 후보가 줄어도 final/timing gate를 유지하는 범위에서 signature/general backlog를
  보충하는 refill을 도입했다.
- handoff playbook의 rescue budget을 기본 실행에 자동 적용했다.
- 실행 큐를 `auto_ready`/`manual_review`/`needs_enrichment`로 분리하고, `final_queue_v2` evidence
  계약으로 낮은 정보량 후보의 priority 과포화를 막았다.

## 2026-07-12: 결과 재정합과 운영 메모 정리

- Legion scan 109(9,237 keywords) 뒤 Viral Hunter 결과를 심층 검토했다.
- 오래된 `running` scan_run 16건을 실제 worker 부재 확인 후 실패 상태로 정리했다.
- 본문/게시일 재검증 46건에서 광고·시점 문제를 재게이트했고, 최근 스캔 기준 body enrichment
  선택으로 재발견 후보 누락을 방지했다.
- 3,774건의 최근 스캔 행에 quality metric을 backfill해 metric coverage를 100%로 만들었다.
- DB 최종 상태와 legacy CSV의 불일치를 재정합했다. 최종 실행 export는 자동 2, 수동 1,
  보강 15건이며, 원본 39건 중 21건은 차단/만료/삭제 상태로 제외됐다.
- 이후 실행은 DB persisted status를 reload한 뒤 alert/export하므로, DB가 차단한 후보가
  in-memory `pending` 상태만으로 자동 실행 export에 다시 들어가지 않는다.

## 2026-07-20: scan 117·118 결과와 운영 판단

- Legion scan `117`은 9,279개 키워드를 처리했고 S/A는 2,060개( S 78, A 1,982)였다. 전체 discovery source-diversity는
  목표보다 낮았지만(`0.421 < 0.45`), S/A 후보군은 post-seed expansion source가 주도했으므로 blind source cap은 적용하지 않는다.
- Viral scan `117`은 910개 target을 저장했다. quality metric backfill은 백업 확인 후 불완전 행 646개에 적용했으며,
  coverage 개선을 eligibility 승격으로 해석하지 않는다. handoff audit은 critical(37.96)이었다.
- Legion scan `118`은 9,257개 키워드( S 92, A 1,934)를 처리했다. Viral funnel은 raw 2,247 → rule/batch survivor 471 →
  final execution 13(automatic 2, manual 6, enrichment 5)이며, survivor 중 기존 URL이 433개였다. 다음 개선은 게이트 완화가 아니라 discovery breadth다.
- scan 118 audit도 critical(30.48)이었고 주요 원인은 region ambiguity와 Pathfinder mismatch였다. variant/source feedback은 다음 계획에 반영하되
  medical·locality·AI·freshness·final execution gate는 유지한다.

## 2026-07-21: Legion 120·Viral audit 교정

- Legion scan `120`은 9,293개 키워드를 처리했다(신규 313, 갱신 8,980; S 83, A 1,944, B 6,819, C 447).
- Viral audit snapshot은 discovered 3,368개였지만 fresh는 362개, rediscovered는 3,006개였고 fresh pending은 0개였다. 따라서 저장량을 신규 실행 기회로 해석하지 않고 discovery breadth 문제로 분류한다.
- category detector의 빈 값을 fallback `기타`로 세던 오류를 수정해 content-category mismatch가 28.87%에서 15.66%로 교정됐다. 빈 검출값은 unknown이며 mismatch 계산에서 제외한다.
- enrichment 후 AI 후보의 변동 원인을 first-pass 생존자, 일반 refill, discarded-backlog refill로 분리해 `run_funnel`에 기록하도록 보강했다. 이 지표들은 final/timing gate를 완화하지 않는 관측성 개선이다.
