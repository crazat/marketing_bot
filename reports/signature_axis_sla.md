# 시그니처 축 SLA 리포트
_생성: 2026-06-21T12:24:40 · read-only_

## 1. 골든큐 상태 (viral_targets)
- **흉터/여드름흉터**: pending 0 · raw_backlog 18 · posted 48 · generated 2 · skipped 269
- **안면비대칭**: pending 13 · raw_backlog 912 · posted 46 · generated 2 · skipped 399

## 2. 백로그 윈도우 갭 — Lane A 가 메우는 starvation
- **흉터/여드름흉터**: 일반 레스큐(21일) 4건 → 시그니처 레인(180일) 18건 (**+14 해금**)
- **안면비대칭**: 일반 레스큐(21일) 0건 → 시그니처 레인(180일) 912건 (**+912 해금**)

## 3. Q&A 지식 커버리지 — Lane B (축당 ≥1 목표)
- **흉터/여드름흉터**: 5개 ✅
- **안면비대칭**: 4개 ✅

## 4. 자체 콘텐츠 랭크 — Lane C (발행 후 추적)
- `청주 패인흉터 여드름 비용`: rank 0 (no_results) 2026-06-09 07:49:18
- `청주 패인흉터 여드름 상담`: rank 0 (no_results) 2026-06-09 07:48:59
- `청주 패인흉터 여드름 한의원 비용`: rank 0 (no_results) 2026-06-09 07:48:58
- `청주 패인흉터 여드름 한의원 상담`: rank 0 (no_results) 2026-06-09 07:48:44
- `청주 패인흉터 여드름흉터 비용`: rank 0 (no_results) 2026-06-09 07:48:24
- `청주 패인흉터 여드름흉터 상담`: rank 0 (no_results) 2026-06-09 07:47:48
- `청주 여드름흉터 가격표`: rank 0 (no_results) 2026-06-09 07:42:49
- `청주안면비대칭`: rank 1 (found) 2026-06-09 07:42:06
- `청주여드름흉터치료`: rank 0 (not_in_results) 2026-06-09 07:38:12
- `청주여드름흉터`: rank 1 (found) 2026-06-09 07:37:25
- `청주 여드름흉터 한의원`: rank 4 (found) 2026-06-09 07:23:48
- `오창 안면비대칭`: rank 0 (no_results) 2026-06-09 07:22:54

## 5. 발견 퍼널 트렌드 (최근 스캔)

**흉터/여드름흉터**  (fresh / pending / ad_filtered / rejected)
- #6 2026-06-16 23:24: fresh 0 · pending 15 · ad 346 · reject 1083
- #7 2026-06-17 21:42: fresh 0 · pending 32 · ad 456 · reject 1323
- #8 2026-06-19 19:44: fresh 349 · pending 39 · ad 225 · reject 1272
- #9 2026-06-20 11:33: fresh 237 · pending 27 · ad 246 · reject 1063
- #10 2026-06-21 10:44: fresh 146 · pending 30 · ad 285 · reject 1057
- #11 2026-06-21 11:28: fresh 239 · pending 32 · ad 338 · reject 1335

**안면비대칭**  (fresh / pending / ad_filtered / rejected)
- #6 2026-06-16 23:24: fresh 0 · pending 7 · ad 255 · reject 1100
- #7 2026-06-17 21:42: fresh 0 · pending 36 · ad 352 · reject 1541
- #8 2026-06-19 19:44: fresh 132 · pending 29 · ad 252 · reject 1570
- #9 2026-06-20 11:33: fresh 120 · pending 31 · ad 435 · reject 1462
- #10 2026-06-21 10:44: fresh 12 · pending 26 · ad 427 · reject 1386
- #11 2026-06-21 11:28: fresh 200 · pending 28 · ad 453 · reject 1616

## 6. SLA 판정
- **흉터/여드름흉터**: Q&A OK · 백로그공급 18 · pending 15↑32
- **안면비대칭**: Q&A OK · 백로그공급 912 · pending 7↑28
