/**
 * 콘텐츠 제안 생성기
 * S/A급 키워드를 기반으로 블로그 콘텐츠 제안을 생성합니다.
 */

export interface Keyword {
  keyword: string
  search_volume: number
  grade: string
  difficulty: number
  opportunity: number
  category: string
  trend_status: string
  search_intent?: string
}

export interface ContentSuggestion {
  title: string
  keywords: string[]
  category: string
  contentType: ContentType
  outline: string[]
  targetAudience: string
  estimatedSearchVolume: number
  difficulty: 'easy' | 'medium' | 'hard'
  priority: number
}

type ContentType = 'howto' | 'comparison' | 'review' | 'guide' | 'faq' | 'case-study'

/**
 * 콘텐츠 유형별 템플릿
 */
const CONTENT_TEMPLATES: Record<ContentType, {
  titleFormats: string[]
  outlineTemplate: string[]
}> = {
  howto: {
    titleFormats: [
      '{keyword} 방법 완벽 가이드',
      '{keyword}, 이렇게 하면 됩니다',
      '초보자를 위한 {keyword} 가이드',
    ],
    outlineTemplate: [
      '1. {keyword}란 무엇인가?',
      '2. {keyword}가 필요한 경우',
      '3. {keyword} 단계별 방법',
      '4. 주의사항 및 팁',
      '5. 자주 묻는 질문',
    ],
  },
  comparison: {
    titleFormats: [
      '{keyword} 비교 분석 (장단점 총정리)',
      '{keyword} vs 다른 방법, 무엇이 좋을까?',
      '2026년 {keyword} 비교 가이드',
    ],
    outlineTemplate: [
      '1. 비교 기준 소개',
      '2. 방법별 장단점',
      '3. 비용 비교',
      '4. 효과 비교',
      '5. 추천 선택 가이드',
    ],
  },
  review: {
    titleFormats: [
      '{keyword} 실제 후기 (솔직 리뷰)',
      '{keyword} 경험담 공유',
      '{keyword} 3개월 후기',
    ],
    outlineTemplate: [
      '1. 선택하게 된 이유',
      '2. 실제 경험 후기',
      '3. 장점과 단점',
      '4. 비용 및 기간',
      '5. 추천 여부',
    ],
  },
  guide: {
    titleFormats: [
      '{keyword} 완벽 가이드 2026',
      '처음부터 끝까지 {keyword} 총정리',
      '{keyword} A to Z',
    ],
    outlineTemplate: [
      '1. 개요 및 기본 정보',
      '2. 종류와 특징',
      '3. 선택 시 고려사항',
      '4. 진행 과정',
      '5. 예상 비용',
      '6. 마무리 및 관리',
    ],
  },
  faq: {
    titleFormats: [
      '{keyword} 자주 묻는 질문 TOP 10',
      '{keyword}에 대해 궁금한 모든 것',
      '{keyword} Q&A 총정리',
    ],
    outlineTemplate: [
      '1. {keyword}란?',
      '2. 비용은 얼마인가요?',
      '3. 기간은 얼마나 걸리나요?',
      '4. 부작용은 없나요?',
      '5. 어떤 사람에게 추천하나요?',
    ],
  },
  'case-study': {
    titleFormats: [
      '{keyword} 성공 사례 모음',
      '실제 {keyword} 케이스 분석',
      '{keyword} 전후 비교 사례',
    ],
    outlineTemplate: [
      '1. 사례 소개',
      '2. 진행 과정',
      '3. 결과 및 효과',
      '4. 성공 요인 분석',
      '5. 적용 팁',
    ],
  },
}

/**
 * 카테고리별 타겟 오디언스
 */
const CATEGORY_AUDIENCES: Record<string, string> = {
  '다이어트': '체중 감량을 원하는 20-50대',
  '피부': '피부 고민이 있는 10-40대',
  '교통사고': '교통사고 후 치료가 필요한 분들',
  '체형교정': '자세 교정이 필요한 직장인/학생',
  '탈모': '탈모 고민이 있는 30-50대',
  '통증': '만성 통증으로 고생하는 분들',
  '한방': '한방 치료에 관심 있는 분들',
  '기타': '건강 관리에 관심 있는 분들',
}

/**
 * 키워드에서 콘텐츠 유형 추론
 */
function inferContentType(keyword: string, intent?: string): ContentType {
  const lower = keyword.toLowerCase()

  if (intent === 'informational' || lower.includes('방법') || lower.includes('하는법')) {
    return 'howto'
  }
  if (lower.includes('비교') || lower.includes('vs') || lower.includes('차이')) {
    return 'comparison'
  }
  if (lower.includes('후기') || lower.includes('리뷰') || lower.includes('경험')) {
    return 'review'
  }
  if (lower.includes('질문') || lower.includes('궁금')) {
    return 'faq'
  }
  if (lower.includes('사례') || lower.includes('전후')) {
    return 'case-study'
  }

  return 'guide'
}

/**
 * 난이도 계산
 */
function calculateDifficulty(keyword: Keyword): 'easy' | 'medium' | 'hard' {
  if (keyword.difficulty <= 30) return 'easy'
  if (keyword.difficulty <= 60) return 'medium'
  return 'hard'
}

/**
 * 우선순위 점수 계산
 */
function calculatePriority(keyword: Keyword): number {
  let score = 0

  // 등급 점수
  if (keyword.grade === 'S') score += 40
  else if (keyword.grade === 'A') score += 30
  else if (keyword.grade === 'B') score += 20
  else score += 10

  // 검색량 점수 (로그 스케일)
  score += Math.min(Math.log10(keyword.search_volume + 1) * 10, 30)

  // 기회 점수
  score += keyword.opportunity * 0.2

  // 트렌드 보너스
  if (keyword.trend_status === 'rising') score += 10

  return Math.round(score)
}

/**
 * 단일 키워드에서 콘텐츠 제안 생성
 */
export function generateSuggestion(keyword: Keyword): ContentSuggestion {
  const contentType = inferContentType(keyword.keyword, keyword.search_intent)
  const template = CONTENT_TEMPLATES[contentType]

  // 제목 선택 (랜덤)
  const titleFormat = template.titleFormats[
    Math.floor(Math.random() * template.titleFormats.length)
  ]
  const title = titleFormat.replace('{keyword}', keyword.keyword)

  // 아웃라인 생성
  const outline = template.outlineTemplate.map(item =>
    item.replace('{keyword}', keyword.keyword)
  )

  return {
    title,
    keywords: [keyword.keyword],
    category: keyword.category,
    contentType,
    outline,
    targetAudience: CATEGORY_AUDIENCES[keyword.category] || CATEGORY_AUDIENCES['기타'],
    estimatedSearchVolume: keyword.search_volume,
    difficulty: calculateDifficulty(keyword),
    priority: calculatePriority(keyword),
  }
}

/**
 * 키워드 클러스터에서 통합 콘텐츠 제안 생성
 */
export function generateClusterSuggestion(
  keywords: Keyword[],
  clusterName: string
): ContentSuggestion {
  if (keywords.length === 0) {
    throw new Error('키워드가 없습니다')
  }

  // 대표 키워드 선택 (검색량 기준)
  const mainKeyword = keywords.reduce((a, b) =>
    a.search_volume > b.search_volume ? a : b
  )

  const contentType = inferContentType(mainKeyword.keyword, mainKeyword.search_intent)
  const template = CONTENT_TEMPLATES[contentType]

  // 제목 생성
  const titleFormat = template.titleFormats[0]
  const title = titleFormat.replace('{keyword}', clusterName)

  // 모든 키워드를 아웃라인에 반영
  const outline = [
    `1. ${clusterName} 개요`,
    ...keywords.slice(0, 5).map((kw, i) => `${i + 2}. ${kw.keyword} 상세 정보`),
    `${Math.min(keywords.length, 5) + 2}. 정리 및 추천`,
  ]

  // 총 검색량
  const totalVolume = keywords.reduce((sum, kw) => sum + kw.search_volume, 0)

  // 평균 난이도
  const avgDifficulty = keywords.reduce((sum, kw) => sum + kw.difficulty, 0) / keywords.length

  return {
    title,
    keywords: keywords.map(kw => kw.keyword),
    category: mainKeyword.category,
    contentType,
    outline,
    targetAudience: CATEGORY_AUDIENCES[mainKeyword.category] || CATEGORY_AUDIENCES['기타'],
    estimatedSearchVolume: totalVolume,
    difficulty: avgDifficulty <= 30 ? 'easy' : avgDifficulty <= 60 ? 'medium' : 'hard',
    priority: Math.max(...keywords.map(calculatePriority)),
  }
}

/**
 * 여러 키워드에서 콘텐츠 제안 목록 생성
 */
export function generateSuggestions(
  keywords: Keyword[],
  options: { limit?: number; minGrade?: string } = {}
): ContentSuggestion[] {
  const { limit = 10, minGrade = 'B' } = options

  // 등급 필터링
  const gradeOrder = ['S', 'A', 'B', 'C']
  const minGradeIndex = gradeOrder.indexOf(minGrade)
  const filtered = keywords.filter(
    kw => gradeOrder.indexOf(kw.grade) <= minGradeIndex
  )

  // 제안 생성
  const suggestions = filtered.map(generateSuggestion)

  // 우선순위순 정렬
  suggestions.sort((a, b) => b.priority - a.priority)

  return suggestions.slice(0, limit)
}

/**
 * 콘텐츠 캘린더 생성 (주간)
 */
export function generateWeeklyCalendar(
  keywords: Keyword[]
): Array<{ day: string; suggestion: ContentSuggestion | null }> {
  const days = ['월', '화', '수', '목', '금']
  const suggestions = generateSuggestions(keywords, { limit: 5, minGrade: 'A' })

  return days.map((day, index) => ({
    day,
    suggestion: suggestions[index] || null,
  }))
}

/**
 * 콘텐츠 유형별 통계
 */
export function getContentTypeStats(
  suggestions: ContentSuggestion[]
): Record<ContentType, number> {
  const stats: Record<ContentType, number> = {
    howto: 0,
    comparison: 0,
    review: 0,
    guide: 0,
    faq: 0,
    'case-study': 0,
  }

  suggestions.forEach(s => {
    stats[s.contentType]++
  })

  return stats
}
