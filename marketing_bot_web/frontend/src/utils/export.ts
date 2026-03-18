/**
 * 데이터 내보내기 유틸리티
 */

/**
 * 데이터를 CSV 형식으로 내보내기
 */
export function exportToCSV<T extends object>(
  data: T[],
  columns: { key: string; label: string }[],
  filename: string = 'export.csv'
): void {
  if (!data || data.length === 0) {
    console.warn('내보낼 데이터가 없습니다.')
    return
  }

  const headers = columns.map(col => col.label)
  const rows = data.map(row =>
    columns.map(col => {
      const value = (row as Record<string, unknown>)[col.key]
      // CSV 특수문자 처리
      if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
        return `"${value.replace(/"/g, '""')}"`
      }
      return value ?? ''
    })
  )

  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.join(','))
  ].join('\n')

  // BOM 추가 (한글 엑셀 호환)
  const BOM = '\uFEFF'
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8' })
  downloadBlob(blob, filename)
}

/**
 * 데이터를 JSON 형식으로 내보내기
 */
export function exportToJSON<T extends object>(
  data: T[],
  filename: string = 'export.json'
): void {
  if (!data || data.length === 0) {
    console.warn('내보낼 데이터가 없습니다.')
    return
  }

  const jsonContent = JSON.stringify(data, null, 2)
  const blob = new Blob([jsonContent], { type: 'application/json' })
  downloadBlob(blob, filename)
}

/**
 * Blob을 파일로 다운로드
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

/**
 * 키워드 데이터용 내보내기 컬럼 정의
 */
export const KEYWORD_EXPORT_COLUMNS = [
  { key: 'keyword', label: '키워드' },
  { key: 'search_volume', label: '검색량' },
  { key: 'current_rank', label: '현재순위' },
  { key: 'grade', label: '등급' },
  { key: 'difficulty', label: '난이도' },
  { key: 'opportunity', label: '기회점수' },
  { key: 'category', label: '카테고리' },
  { key: 'trend_status', label: '트렌드' },
  { key: 'source', label: '소스' },
]

/**
 * 리드 데이터용 내보내기 컬럼 정의
 */
export const LEAD_EXPORT_COLUMNS = [
  { key: 'title', label: '제목' },
  { key: 'platform', label: '플랫폼' },
  { key: 'category', label: '카테고리' },
  { key: 'status', label: '상태' },
  { key: 'score', label: '점수' },
  { key: 'grade', label: '등급' },
  { key: 'notes', label: '노트' },
  { key: 'contact_info', label: '연락처' },
  { key: 'follow_up_date', label: '팔로업 예정일' },
  { key: 'url', label: 'URL' },
  { key: 'created_at', label: '발견일' },
]

/**
 * 순위 추적 키워드용 내보내기 컬럼 정의
 */
export const RANKING_KEYWORD_EXPORT_COLUMNS = [
  { key: 'keyword', label: '키워드' },
  { key: 'current_rank', label: '현재순위' },
  { key: 'target_rank', label: '목표순위' },
  { key: 'rank_change', label: '순위변화' },
  { key: 'search_volume', label: '검색량' },
  { key: 'category', label: '카테고리' },
  { key: 'status', label: '상태' },
]
