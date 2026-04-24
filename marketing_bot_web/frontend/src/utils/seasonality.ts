/**
 * [BB6] 한의원 키워드 계절성 매핑
 *
 * 월별로 검색량이 오르는 경향이 있는 카테고리.
 * Dashboard 하단에 "이 시기 주목 키워드" 힌트로 노출.
 */

export interface SeasonHint {
  month: number
  trending: string[]
  note: string
}

const SEASON_MAP: Record<number, Omit<SeasonHint, 'month'>> = {
  1: { trending: ['다이어트', '교통사고'], note: '새해 결심·연초 교통사고 증가기' },
  2: { trending: ['다이어트', '탈모'], note: '입학·신학기 준비' },
  3: { trending: ['다이어트', '피부', '비대칭/교정'], note: '봄 환절기 외모 관심 최고' },
  4: { trending: ['피부', '다이어트', '통증/디스크'], note: '야외 활동 증가 → 피부·체형' },
  5: { trending: ['피부', '여성건강'], note: '결혼시즌' },
  6: { trending: ['다이어트', '피부', '두통/어지럼'], note: '초여름 체형 집중' },
  7: { trending: ['다이어트', '피부', '소화기'], note: '여름철 체형·소화' },
  8: { trending: ['다이어트', '호흡기'], note: '휴가철·에어컨 호흡기' },
  9: { trending: ['호흡기', '통증/디스크', '탈모'], note: '환절기 면역·요통' },
  10: { trending: ['통증/디스크', '교통사고', '탈모'], note: '가을 활동 부상' },
  11: { trending: ['통증/디스크', '두통/어지럼'], note: '초겨울 근골격계' },
  12: { trending: ['통증/디스크', '교통사고', '호흡기'], note: '연말 빙판·감기' },
}

/**
 * 특정 월의 계절성 힌트 반환 (1-12).
 */
export function getSeasonHint(month?: number): SeasonHint {
  const m = month ?? new Date().getMonth() + 1
  const data = SEASON_MAP[m] ?? { trending: [], note: '' }
  return { month: m, ...data }
}
