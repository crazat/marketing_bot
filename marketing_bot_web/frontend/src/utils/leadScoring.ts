/**
 * 리드 품질 점수 시스템
 * 리드의 전환 가능성을 예측하고 우선순위를 결정합니다.
 */

export interface Lead {
  id: number
  platform: string
  source: string
  title: string
  content: string
  url: string
  author: string
  status: string
  detected_at: string
  engagement_score?: number
  reply_count?: number
  view_count?: number
}

export interface LeadScore {
  total: number
  grade: 'A' | 'B' | 'C' | 'D'
  factors: ScoreFactor[]
  recommendation: string
}

interface ScoreFactor {
  name: string
  score: number
  maxScore: number
  description: string
}

/**
 * 플랫폼별 기본 가중치
 */
const PLATFORM_WEIGHTS: Record<string, number> = {
  cafe: 25,        // 맘카페 - 높은 전환율
  youtube: 20,     // 유튜브 - 영상 참여도
  instagram: 18,   // 인스타그램 - 시각적 참여
  tiktok: 15,      // 틱톡 - 젊은 층
  carrot: 22,      // 당근마켓 - 지역 기반 높은 의도
  influencer: 28,  // 인플루언서 - 파급력
}

/**
 * 키워드 의도별 가중치
 */
const INTENT_KEYWORDS: Record<string, { keywords: string[]; weight: number }> = {
  transactional: {
    keywords: ['가격', '비용', '후기', '예약', '상담', '추천', '어디'],
    weight: 30,
  },
  informational: {
    keywords: ['방법', '효과', '증상', '원인', '치료'],
    weight: 15,
  },
  navigational: {
    keywords: ['청주', '한의원', '병원', '의원', '클리닉'],
    weight: 20,
  },
}

/**
 * 시간 기반 신선도 점수 계산
 */
function calculateFreshnessScore(detectedAt: string): number {
  const now = new Date()
  const detected = new Date(detectedAt)
  const hoursAgo = (now.getTime() - detected.getTime()) / (1000 * 60 * 60)

  if (hoursAgo < 6) return 25      // 6시간 이내 - 최고 신선도
  if (hoursAgo < 24) return 20     // 24시간 이내
  if (hoursAgo < 72) return 15     // 3일 이내
  if (hoursAgo < 168) return 10    // 1주일 이내
  return 5                          // 그 이상
}

/**
 * 콘텐츠 품질 점수 계산
 */
function calculateContentScore(title: string, content: string): number {
  let score = 0
  const text = `${title} ${content}`.toLowerCase()

  // 의도 키워드 매칭
  for (const [, config] of Object.entries(INTENT_KEYWORDS)) {
    const matches = config.keywords.filter(kw => text.includes(kw))
    if (matches.length > 0) {
      score += Math.min(config.weight, matches.length * 10)
    }
  }

  // 콘텐츠 길이 보너스
  if (content.length > 200) score += 5
  if (content.length > 500) score += 5

  // 질문 형태 보너스 (높은 참여 의도)
  if (text.includes('?') || text.includes('어디') || text.includes('추천')) {
    score += 10
  }

  return Math.min(score, 30)
}

/**
 * 참여도 점수 계산
 */
function calculateEngagementScore(lead: Lead): number {
  let score = 0

  if (lead.engagement_score) {
    score += Math.min(lead.engagement_score / 10, 15)
  }

  if (lead.reply_count) {
    score += Math.min(lead.reply_count * 2, 10)
  }

  if (lead.view_count) {
    score += Math.min(Math.log10(lead.view_count + 1) * 3, 10)
  }

  return score
}

/**
 * 리드 품질 점수 계산
 */
export function calculateLeadScore(lead: Lead): LeadScore {
  const factors: ScoreFactor[] = []

  // 1. 플랫폼 점수
  const platformScore = PLATFORM_WEIGHTS[lead.platform] || 10
  factors.push({
    name: '플랫폼',
    score: platformScore,
    maxScore: 28,
    description: `${lead.platform} 플랫폼 기본 점수`,
  })

  // 2. 신선도 점수
  const freshnessScore = calculateFreshnessScore(lead.detected_at)
  factors.push({
    name: '신선도',
    score: freshnessScore,
    maxScore: 25,
    description: '발견 시점 기준 신선도',
  })

  // 3. 콘텐츠 점수
  const contentScore = calculateContentScore(lead.title, lead.content)
  factors.push({
    name: '콘텐츠',
    score: contentScore,
    maxScore: 30,
    description: '키워드 의도 및 콘텐츠 품질',
  })

  // 4. 참여도 점수
  const engagementScore = calculateEngagementScore(lead)
  factors.push({
    name: '참여도',
    score: engagementScore,
    maxScore: 25,
    description: '조회수, 댓글 등 참여 지표',
  })

  // 총점 계산
  const total = factors.reduce((sum, f) => sum + f.score, 0)

  // 등급 결정
  let grade: 'A' | 'B' | 'C' | 'D'
  let recommendation: string

  if (total >= 80) {
    grade = 'A'
    recommendation = '즉시 연락 권장 - 높은 전환 가능성'
  } else if (total >= 60) {
    grade = 'B'
    recommendation = '우선 연락 대상 - 좋은 기회'
  } else if (total >= 40) {
    grade = 'C'
    recommendation = '모니터링 필요 - 추가 정보 수집'
  } else {
    grade = 'D'
    recommendation = '낮은 우선순위 - 장기 관찰'
  }

  return { total, grade, factors, recommendation }
}

/**
 * 리드 배열을 점수순으로 정렬
 */
export function sortLeadsByScore(leads: Lead[]): Array<Lead & { score: LeadScore }> {
  return leads
    .map(lead => ({
      ...lead,
      score: calculateLeadScore(lead),
    }))
    .sort((a, b) => b.score.total - a.score.total)
}

/**
 * 리드 등급별 통계
 */
export function getLeadGradeStats(leads: Lead[]): Record<string, number> {
  const stats = { A: 0, B: 0, C: 0, D: 0 }

  leads.forEach(lead => {
    const { grade } = calculateLeadScore(lead)
    stats[grade]++
  })

  return stats
}

/**
 * 플랫폼별 평균 점수
 */
export function getPlatformAverageScores(leads: Lead[]): Record<string, number> {
  const platformScores: Record<string, number[]> = {}

  leads.forEach(lead => {
    const { total } = calculateLeadScore(lead)
    if (!platformScores[lead.platform]) {
      platformScores[lead.platform] = []
    }
    platformScores[lead.platform].push(total)
  })

  const averages: Record<string, number> = {}
  for (const [platform, scores] of Object.entries(platformScores)) {
    averages[platform] = Math.round(
      scores.reduce((a, b) => a + b, 0) / scores.length
    )
  }

  return averages
}
