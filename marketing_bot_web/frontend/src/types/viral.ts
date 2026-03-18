/**
 * Viral Hunter 타입 정의
 */

// 바이럴 타겟 인터페이스
export interface ViralTargetData {
  id: string
  title: string
  url: string
  platform: string
  content_preview?: string
  matched_keywords?: string[]
  category?: string
  priority_score?: number
  comment_status?: string
  scan_count?: number
  discovered_at?: string
  last_scanned_at?: string
  like_count?: number
  comment_count?: number
  view_count?: number
  is_commentable?: boolean
  generated_comment?: string
  author?: string
}

// 카테고리 통계
export interface CategoryStat {
  count: number
  scores: number[]
  maxScore: number
}

export interface CategoryStatResult {
  category: string
  count: number
  avgScore: number
  maxScore: number
  priority: number
}

// 플랫폼 통계
export interface PlatformStat {
  count: number
  avgScore: number
  maxScore: number
}

// 스캔 배치
export interface ScanBatch {
  batch_id: string
  batch_label: string
  batch_date: string
  batch_hour: number
  count: number
}

// 필터 상태
export interface ViralFilterState {
  date_filter?: string
  platforms?: string[]
  status?: string
  category?: string
  comment_status?: string
  min_scan_count?: number
  search?: string
  sort?: string
  scan_batch?: string
}

// 대량 액션 확인
export interface BulkActionConfirm {
  action: 'approve' | 'skip' | 'delete'
  count: number
}

// 생성 진행률
export interface GenerationProgress {
  current: number
  total: number
}

// 검증 결과
export interface VerifyResults {
  total: number
  commentable: number
  not_commentable: number
}

// 완료 통계
export interface CompletionStats {
  approved: number
  skipped: number
  deleted: number
}

// 리드 추적 모달 상태
export interface LeadTrackingModalState {
  isOpen: boolean
  targetTitle: string
  leadCreated: boolean
}

// 스캔 설정
export interface ScanSettings {
  platforms: string[]
  maxResults: number
}

// 카테고리 매핑 (키워드 패턴)
export const CATEGORY_MAPPING: Record<string, string[]> = {
  '다이어트': ['다이어트', '살빼', '체중', '비만', '감량', '산후다이어트', '살빼기'],
  '비대칭/교정': ['비대칭', '안면비대칭', '얼굴비대칭', '체형교정', '골반', '교정'],
  '피부': ['피부', '여드름', '리프팅', '주름', '탄력', '흉터', '트러블', '피부관리'],
  '교통사고': ['교통사고', '자동차사고', '사고치료', '교통사고입원', '사고후유증'],
  '통증/디스크': ['허리', '목', '어깨', '무릎', '통증', '디스크', '추나', '도수', '요통'],
  '두통/어지럼': ['두통', '편두통', '어지럼', '어지러움', '현훈'],
  '소화기': ['소화', '위염', '역류', '설사', '변비', '소화불량'],
  '호흡기': ['감기', '비염', '알레르기', '천식', '기침'],
  '기타증상': ['이석증', '탈모', '다한증', '불면', '수면', '불면증'],
}

// 플랫폼 아이콘 및 라벨
export const PLATFORM_INFO: Record<string, { icon: string; label: string }> = {
  cafe: { icon: '☕', label: '네이버 카페' },
  blog: { icon: '📝', label: '블로그' },
  kin: { icon: '❓', label: '지식iN' },
  youtube: { icon: '📺', label: '유튜브' },
  instagram: { icon: '📸', label: '인스타그램' },
  tiktok: { icon: '🎵', label: '틱톡' },
  place: { icon: '📍', label: '플레이스' },
  karrot: { icon: '🥕', label: '당근' },
  other: { icon: '📌', label: '기타' },
}

// 플랫폼 라벨 (간단 버전)
export const PLATFORM_LABELS: Record<string, string> = {
  cafe: '카페',
  blog: '블로그',
  kin: '지식인',
  youtube: 'YouTube',
  instagram: '인스타',
  tiktok: 'TikTok',
  place: '플레이스',
  karrot: '당근',
  other: '기타',
}

// 카테고리 목록
export const CATEGORIES = [
  '다이어트', '비대칭/교정', '피부', '교통사고',
  '통증/디스크', '두통/어지럼', '소화기', '호흡기', '기타'
]

// 댓글 상태 옵션
export const COMMENT_STATUS_OPTIONS = [
  { value: 'pending', label: '대기중' },
  { value: 'generated', label: 'AI 생성됨' },
  { value: 'approved', label: '승인됨' },
  { value: 'posted', label: '게시됨' },
  { value: 'skipped', label: '건너뜀' },
]

// 자동 카테고리 분류 함수
export function autoCategorize(title: string, keywords: string[]): string {
  const text = `${title} ${keywords.join(' ')}`.toLowerCase()

  for (const [category, patterns] of Object.entries(CATEGORY_MAPPING)) {
    if (patterns.some(pattern => text.includes(pattern.toLowerCase()))) {
      return category
    }
  }

  return '기타'
}

// 카테고리 통계 계산 함수
export function calculateCategoryStats(targets: ViralTargetData[]): CategoryStatResult[] {
  const stats: Record<string, CategoryStat> = {}

  targets.forEach(target => {
    const keywords = Array.isArray(target.matched_keywords)
      ? target.matched_keywords
      : []
    const category = autoCategorize(target.title || '', keywords)

    if (!stats[category]) {
      stats[category] = {
        count: 0,
        scores: [],
        maxScore: 0,
      }
    }

    stats[category].count++
    const score = target.priority_score || 0
    stats[category].scores.push(score)
    stats[category].maxScore = Math.max(stats[category].maxScore, score)
  })

  // 평균 및 우선순위 계산
  const result = Object.entries(stats).map(([category, data]) => {
    const avgScore = data.scores.length > 0
      ? data.scores.reduce((a: number, b: number) => a + b, 0) / data.scores.length
      : 0
    const priority = data.maxScore * 0.5 + avgScore * 0.3 + data.count * 0.2

    return {
      category,
      count: data.count,
      avgScore,
      maxScore: data.maxScore,
      priority,
    }
  })

  // 우선순위 순 정렬
  return result.sort((a, b) => b.priority - a.priority)
}

// 플랫폼 정규화 함수
export function normalizePlatform(platform: string | undefined | null): string {
  if (!platform) return 'other'
  const p = platform.toLowerCase().trim()

  if (p.includes('cafe') || p.includes('카페')) return 'cafe'
  if (p.includes('blog') || p.includes('블로그')) return 'blog'
  if (p.includes('kin') || p.includes('지식')) return 'kin'
  if (p.includes('youtube') || p.includes('유튜브')) return 'youtube'
  if (p.includes('instagram') || p.includes('인스타')) return 'instagram'
  if (p.includes('tiktok') || p.includes('틱톡')) return 'tiktok'
  if (p.includes('place') || p.includes('플레이스')) return 'place'
  if (p.includes('karrot') || p.includes('당근')) return 'karrot'

  return 'other'
}
