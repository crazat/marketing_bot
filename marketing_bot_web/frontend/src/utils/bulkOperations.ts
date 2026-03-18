/**
 * 일괄 작업 유틸리티
 * 키워드 및 리드에 대한 대량 처리 기능을 제공합니다.
 */

export interface BulkOperationResult<T> {
  success: T[]
  failed: Array<{ item: T; error: string }>
  totalProcessed: number
  successCount: number
  failedCount: number
}

export interface KeywordBulkUpdate {
  keyword: string
  updates: Partial<{
    grade: string
    category: string
    status: string
    priority: number
  }>
}

export interface LeadBulkUpdate {
  id: number
  updates: Partial<{
    status: string
    notes: string
    priority: number
  }>
}

/**
 * 키워드 일괄 등급 변경
 */
export async function bulkUpdateKeywordGrades(
  keywords: string[],
  newGrade: string,
  apiCall: (keyword: string, grade: string) => Promise<void>
): Promise<BulkOperationResult<string>> {
  const success: string[] = []
  const failed: Array<{ item: string; error: string }> = []

  for (const keyword of keywords) {
    try {
      await apiCall(keyword, newGrade)
      success.push(keyword)
    } catch (error) {
      failed.push({
        item: keyword,
        error: error instanceof Error ? error.message : '알 수 없는 오류',
      })
    }
  }

  return {
    success,
    failed,
    totalProcessed: keywords.length,
    successCount: success.length,
    failedCount: failed.length,
  }
}

/**
 * 리드 일괄 상태 변경
 */
export async function bulkUpdateLeadStatus(
  leadIds: number[],
  newStatus: string,
  apiCall: (id: number, status: string) => Promise<void>
): Promise<BulkOperationResult<number>> {
  const success: number[] = []
  const failed: Array<{ item: number; error: string }> = []

  for (const id of leadIds) {
    try {
      await apiCall(id, newStatus)
      success.push(id)
    } catch (error) {
      failed.push({
        item: id,
        error: error instanceof Error ? error.message : '알 수 없는 오류',
      })
    }
  }

  return {
    success,
    failed,
    totalProcessed: leadIds.length,
    successCount: success.length,
    failedCount: failed.length,
  }
}

/**
 * 키워드 일괄 카테고리 분류
 */
export function bulkCategorizeKeywords(
  keywords: Array<{ keyword: string; category?: string }>,
  categoryRules: Record<string, string[]>
): Array<{ keyword: string; category: string; confidence: 'high' | 'medium' | 'low' }> {
  return keywords.map(kw => {
    let matchedCategory = '기타'
    let confidence: 'high' | 'medium' | 'low' = 'low'

    for (const [category, patterns] of Object.entries(categoryRules)) {
      const matches = patterns.filter(pattern =>
        kw.keyword.toLowerCase().includes(pattern.toLowerCase())
      )

      if (matches.length > 0) {
        matchedCategory = category
        confidence = matches.length >= 2 ? 'high' : 'medium'
        break
      }
    }

    return {
      keyword: kw.keyword,
      category: matchedCategory,
      confidence,
    }
  })
}

/**
 * 키워드 중복 제거 및 병합
 */
export function deduplicateKeywords<T extends { keyword: string }>(
  keywords: T[],
  mergeStrategy: 'first' | 'last' | 'highest-volume' = 'first'
): T[] {
  const keywordMap = new Map<string, T>()

  for (const kw of keywords) {
    const normalizedKeyword = kw.keyword.toLowerCase().trim()
    const existing = keywordMap.get(normalizedKeyword)

    if (!existing) {
      keywordMap.set(normalizedKeyword, kw)
    } else if (mergeStrategy === 'last') {
      keywordMap.set(normalizedKeyword, kw)
    } else if (mergeStrategy === 'highest-volume') {
      const existingVolume = (existing as unknown as { search_volume?: number }).search_volume || 0
      const currentVolume = (kw as unknown as { search_volume?: number }).search_volume || 0
      if (currentVolume > existingVolume) {
        keywordMap.set(normalizedKeyword, kw)
      }
    }
  }

  return Array.from(keywordMap.values())
}

/**
 * 키워드 필터링 (다중 조건)
 */
export function filterKeywords<T extends Record<string, unknown>>(
  keywords: T[],
  filters: {
    grade?: string[]
    category?: string[]
    minVolume?: number
    maxVolume?: number
    minOpportunity?: number
    trendStatus?: string[]
    searchText?: string
  }
): T[] {
  return keywords.filter(kw => {
    // 등급 필터
    if (filters.grade?.length && !filters.grade.includes(kw.grade as string)) {
      return false
    }

    // 카테고리 필터
    if (filters.category?.length && !filters.category.includes(kw.category as string)) {
      return false
    }

    // 검색량 범위 필터
    const volume = kw.search_volume as number
    if (filters.minVolume !== undefined && volume < filters.minVolume) {
      return false
    }
    if (filters.maxVolume !== undefined && volume > filters.maxVolume) {
      return false
    }

    // 기회점수 필터
    if (filters.minOpportunity !== undefined) {
      const opportunity = kw.opportunity as number
      if (opportunity < filters.minOpportunity) {
        return false
      }
    }

    // 트렌드 필터
    if (filters.trendStatus?.length && !filters.trendStatus.includes(kw.trend_status as string)) {
      return false
    }

    // 텍스트 검색
    if (filters.searchText) {
      const keyword = (kw.keyword as string).toLowerCase()
      if (!keyword.includes(filters.searchText.toLowerCase())) {
        return false
      }
    }

    return true
  })
}

/**
 * 리드 필터링 (다중 조건)
 */
export function filterLeads<T extends Record<string, unknown>>(
  leads: T[],
  filters: {
    platform?: string[]
    status?: string[]
    minScore?: number
    dateFrom?: Date
    dateTo?: Date
    searchText?: string
  }
): T[] {
  return leads.filter(lead => {
    // 플랫폼 필터
    if (filters.platform?.length && !filters.platform.includes(lead.platform as string)) {
      return false
    }

    // 상태 필터
    if (filters.status?.length && !filters.status.includes(lead.status as string)) {
      return false
    }

    // 점수 필터
    if (filters.minScore !== undefined) {
      const score = lead.score as number
      if (score < filters.minScore) {
        return false
      }
    }

    // 날짜 범위 필터
    const detectedAt = new Date(lead.detected_at as string)
    if (filters.dateFrom && detectedAt < filters.dateFrom) {
      return false
    }
    if (filters.dateTo && detectedAt > filters.dateTo) {
      return false
    }

    // 텍스트 검색
    if (filters.searchText) {
      const searchLower = filters.searchText.toLowerCase()
      const title = (lead.title as string || '').toLowerCase()
      const content = (lead.content as string || '').toLowerCase()
      if (!title.includes(searchLower) && !content.includes(searchLower)) {
        return false
      }
    }

    return true
  })
}

/**
 * 선택 항목 관리 헬퍼
 */
export function createSelectionManager<T extends { id: string | number }>(
  items: T[]
) {
  let selected = new Set<string | number>()

  return {
    getSelected: () => Array.from(selected),
    getSelectedItems: () => items.filter(item => selected.has(item.id)),
    isSelected: (id: string | number) => selected.has(id),
    toggle: (id: string | number) => {
      if (selected.has(id)) {
        selected.delete(id)
      } else {
        selected.add(id)
      }
      return Array.from(selected)
    },
    selectAll: () => {
      selected = new Set(items.map(item => item.id))
      return Array.from(selected)
    },
    clearAll: () => {
      selected.clear()
      return []
    },
    selectByCondition: (condition: (item: T) => boolean) => {
      items.forEach(item => {
        if (condition(item)) {
          selected.add(item.id)
        }
      })
      return Array.from(selected)
    },
    count: () => selected.size,
  }
}

/**
 * 일괄 내보내기 준비
 */
export function prepareBulkExport<T extends Record<string, unknown>>(
  items: T[],
  columns: Array<{ key: string; label: string; formatter?: (value: unknown) => string }>
): {
  headers: string[]
  rows: string[][]
} {
  const headers = columns.map(col => col.label)
  const rows = items.map(item =>
    columns.map(col => {
      const value = item[col.key]
      if (col.formatter) {
        return col.formatter(value)
      }
      if (value === null || value === undefined) {
        return ''
      }
      return String(value)
    })
  )

  return { headers, rows }
}
