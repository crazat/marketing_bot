/**
 * 도메인 용어 사전 — priority_score, KEI, grade 등
 *
 * 신규 사용자가 숫자 의미를 모를 때 툴팁으로 개념 설명.
 * GlossaryTerm 컴포넌트에서 이 테이블 참조.
 */

export interface GlossaryEntry {
  term: string
  short: string
  detail?: string
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  priority_score: {
    term: 'Priority Score',
    short: '타겟 처리 우선순위 (0–150+)',
    detail:
      '리드 가능성·신선도·경쟁 강도·플랫폼 가중치를 합산한 점수. 80+ HOT, 100+ Tier 1.',
  },
  hot_lead: {
    term: 'HOT LEAD',
    short: '우선순위 100+ 고가치 타겟',
    detail:
      '점수 100 이상 — 상담 문의 가능성 높음. 당일 내 처리 권장.',
  },
  kei: {
    term: 'KEI (Keyword Efficiency Index)',
    short: '키워드 효율 지수 = 검색량² / 문서수',
    detail:
      '검색량 대비 경쟁 문서가 적을수록 높음. 높을수록 "쉽게 상위권" 가능.',
  },
  grade_s: {
    term: 'Grade S',
    short: '최상위 등급 키워드',
    detail:
      '검색량·KEI·전환성 모두 상위. 집중 공략 1순위.',
  },
  grade_a: {
    term: 'Grade A',
    short: '우수 등급 키워드',
    detail: '경쟁은 있지만 상위권 진입 가능한 키워드.',
  },
  grade_b: {
    term: 'Grade B',
    short: '보조 키워드',
    detail: '보조 콘텐츠나 롱테일 공략용.',
  },
  grade_c: {
    term: 'Grade C',
    short: '보류 키워드',
    detail: '현재 가치 낮음 — 계절성 체크 후 재평가.',
  },
  engagement_signal_seeking: {
    term: 'Seeking Info',
    short: '정보를 찾는 사용자 신호',
    detail: '질문형 글·비교형 글. 상담 전환 가능성 중.',
  },
  engagement_signal_ready: {
    term: 'Ready to Act',
    short: '즉시 행동 가능한 신호',
    detail: '"어디가 좋나요?" 같은 의사결정 직전 단계. 전환율 최상.',
  },
  engagement_signal_passive: {
    term: 'Passive',
    short: '수동적 탐색 신호',
    detail: '후기/정보 글 — 브랜드 인지 목적으로만 접근.',
  },
  commentable: {
    term: 'Commentable',
    short: '댓글 작성 가능 타겟',
    detail: 'Selenium 검증 완료 — 댓글창이 열려있고 제약 없음.',
  },
  ai_accept_rate: {
    term: 'AI 적합률',
    short: 'AI가 생성한 댓글이 승인된 비율',
    detail:
      '과거 N일간 AI 생성 댓글 중 사용자가 승인한 비율. 40% 이상이면 양호.',
  },
  trust_score: {
    term: 'Trust Score',
    short: '작성자 신뢰도 점수',
    detail: '작성자 활동 이력·답변 품질·평판 기반 점수.',
  },
  scan_batch: {
    term: 'Scan Batch',
    short: '한 번의 스캔 실행으로 발굴된 타겟 묶음',
    detail: '같은 배치 = 같은 시점에 같은 조건으로 수집된 타겟.',
  },
  document_count: {
    term: 'Document Count',
    short: '해당 키워드로 작성된 블로그 문서 수',
    detail: '경쟁 강도 지표. 많을수록 상위 노출이 어려움.',
  },
  search_volume: {
    term: 'Search Volume',
    short: '월 평균 검색량',
    detail: '네이버 키워드 도구 기준 월 추정 검색 횟수.',
  },
}

export function getGlossary(key: string): GlossaryEntry | null {
  return GLOSSARY[key] ?? null
}
