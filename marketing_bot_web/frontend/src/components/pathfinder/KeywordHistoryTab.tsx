import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { pathfinderApi } from '@/services/api'
import type { Keyword, PathfinderStats, ScanRun, DateStat } from '@/types'

// ScanRun에 파싱된 topKeywords를 추가한 타입
interface ParsedScanRun extends ScanRun {
  topKeywords: Keyword[]
}

interface KeywordHistoryTabProps {
  stats: PathfinderStats | null
}

export default function KeywordHistoryTab({ stats: _stats }: KeywordHistoryTabProps) {
  const [viewOption, setViewOption] = useState<'recent7' | 'recent30' | 'custom'>('recent7')
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [historyView, setHistoryView] = useState<'scans' | 'dates'>('scans')

  // 스캔 히스토리 조회
  const { data: scanHistory, isLoading: scanHistoryLoading } = useQuery({
    queryKey: ['pathfinder-scan-history'],
    queryFn: () => pathfinderApi.getScanHistory({ limit: 50 }),
    retry: 1,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 모든 키워드 조회 (created_at 포함)
  const { data: allKeywords, isLoading, isError } = useQuery({
    queryKey: ['pathfinder-all-keywords-history'],
    queryFn: () => pathfinderApi.getKeywords({
      limit: 10000,
    }),
    retry: 1,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 날짜별 그룹화
  const dateStats = useMemo(() => {
    if (!allKeywords) return []

    const statsMap: Record<string, DateStat> = {}

    allKeywords.forEach((kw: Keyword) => {
      if (!kw.created_at) return

      const date = kw.created_at.split('T')[0] // YYYY-MM-DD
      if (!statsMap[date]) {
        statsMap[date] = {
          date,
          total: 0,
          sCount: 0,
          aCount: 0,
          totalVolume: 0,
          sources: {},
          categories: {},
          keywords: [],
        }
      }

      statsMap[date].total++
      statsMap[date].keywords.push(kw)
      if (kw.grade === 'S') statsMap[date].sCount++
      if (kw.grade === 'A') statsMap[date].aCount++
      statsMap[date].totalVolume += kw.search_volume || 0

      // 소스 분포
      const source = kw.source || 'unknown'
      statsMap[date].sources[source] = (statsMap[date].sources[source] || 0) + 1

      // 카테고리 분포
      const category = kw.category || '기타'
      statsMap[date].categories[category] = (statsMap[date].categories[category] || 0) + 1
    })

    return Object.values(statsMap).sort((a, b) => b.date.localeCompare(a.date))
  }, [allKeywords])

  // 필터링된 날짜
  const filteredDates = useMemo(() => {
    if (!dateStats.length) return []

    const now = new Date()
    const cutoff7 = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    const cutoff30 = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)

    if (viewOption === 'recent7') {
      return dateStats.filter((stat) => new Date(stat.date) >= cutoff7)
    } else if (viewOption === 'recent30') {
      return dateStats.filter((stat) => new Date(stat.date) >= cutoff30)
    } else {
      return dateStats.filter((stat) => stat.date === selectedDate)
    }
  }, [dateStats, viewOption, selectedDate])

  // 전체 통계
  const totalStats = useMemo(() => {
    if (!allKeywords) return { total: 0, sCount: 0, aCount: 0, days: 0 }

    const sCount = allKeywords.filter((kw: Keyword) => kw.grade === 'S').length
    const aCount = allKeywords.filter((kw: Keyword) => kw.grade === 'A').length

    return {
      total: allKeywords.length,
      sCount,
      aCount,
      days: dateStats.length,
    }
  }, [allKeywords, dateStats])

  // 스캔 히스토리 파싱 (API 응답은 {runs: [...], total: ...} 형태)
  const parsedScanHistory = useMemo((): ParsedScanRun[] => {
    if (!scanHistory?.runs) return []
    return scanHistory.runs.map((scan: ScanRun): ParsedScanRun => ({
      ...scan,
      topKeywords: scan.top_keywords_json ? JSON.parse(scan.top_keywords_json) : []
    }))
  }, [scanHistory])

  // 실행 시간 포맷
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}초`
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${minutes}분 ${secs}초`
  }

  // 날짜 포맷
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4" />
          <p className="text-muted-foreground">로딩 중...</p>
        </div>
      </div>
    )
  }

  if (isError || !allKeywords || allKeywords.length === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-12 text-center">
        <p className="text-4xl mb-4">📭</p>
        <p className="text-muted-foreground mb-4">히스토리 데이터가 없습니다.</p>
        <p className="text-sm text-muted-foreground">Pathfinder를 실행하여 키워드를 수집하세요.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 뷰 전환 탭 */}
      <div className="flex gap-2 border-b border-border pb-2">
        <button
          onClick={() => setHistoryView('scans')}
          className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
            historyView === 'scans'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted'
          }`}
        >
          🚀 스캔 실행 기록
        </button>
        <button
          onClick={() => setHistoryView('dates')}
          className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
            historyView === 'dates'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted'
          }`}
        >
          📅 날짜별 수집 현황
        </button>
      </div>

      {/* 스캔 실행 기록 뷰 */}
      {historyView === 'scans' && (
        <div className="space-y-6">
          {/* 스캔 통계 요약 */}
          {parsedScanHistory.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-card rounded-lg border border-border p-4 text-center">
                <div className="text-3xl font-bold text-primary">{parsedScanHistory.length}</div>
                <div className="text-sm text-muted-foreground mt-1">총 스캔 횟수</div>
              </div>
              <div className="bg-card rounded-lg border border-border p-4 text-center">
                <div className="text-3xl font-bold text-green-500">
                  {parsedScanHistory.filter((s) => s.status === 'completed').length}
                </div>
                <div className="text-sm text-muted-foreground mt-1">완료</div>
              </div>
              <div className="bg-card rounded-lg border border-border p-4 text-center">
                <div className="text-3xl font-bold text-blue-500">
                  {parsedScanHistory.reduce((sum, s) => sum + (s.total_keywords || 0), 0).toLocaleString()}
                </div>
                <div className="text-sm text-muted-foreground mt-1">총 수집 키워드</div>
              </div>
              <div className="bg-card rounded-lg border border-border p-4 text-center">
                <div className="text-3xl font-bold text-red-500">
                  {parsedScanHistory.reduce((sum, s) => sum + (s.s_grade_count || 0) + (s.a_grade_count || 0), 0).toLocaleString()}
                </div>
                <div className="text-sm text-muted-foreground mt-1">총 S/A급</div>
              </div>
            </div>
          )}

          {/* 스캔 기록 목록 */}
          <div className="bg-card rounded-lg border border-border p-6">
            <h3 className="text-lg font-semibold mb-4">📋 스캔 실행 기록</h3>

            {scanHistoryLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : !parsedScanHistory || parsedScanHistory.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <p className="text-4xl mb-4">🔍</p>
                <p className="font-medium mb-2">스캔 기록이 없습니다</p>
                <p className="text-sm">Pathfinder LEGION 또는 Total War 모드를 실행하면 기록이 저장됩니다.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {parsedScanHistory.map((scan) => (
                  <div
                    key={scan.id}
                    className={`border rounded-lg p-4 transition-colors ${
                      scan.status === 'completed'
                        ? 'border-green-500/30 bg-green-500/5'
                        : scan.status === 'failed'
                        ? 'border-red-500/30 bg-red-500/5'
                        : 'border-yellow-500/30 bg-yellow-500/5'
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold ${
                          scan.mode === 'legion' ? 'bg-purple-500/20 text-purple-500' : 'bg-blue-500/20 text-blue-500'
                        }`}>
                          {scan.mode === 'legion' ? '🎖️' : '⚔️'}
                        </div>
                        <div>
                          <p className="font-semibold">
                            {scan.mode === 'legion' ? 'LEGION MODE' : 'Total War'}
                            <span className={`ml-2 text-xs px-2 py-0.5 rounded ${
                              scan.status === 'completed'
                                ? 'bg-green-500/20 text-green-500'
                                : scan.status === 'failed'
                                ? 'bg-red-500/20 text-red-500'
                                : 'bg-yellow-500/20 text-yellow-500'
                            }`}>
                              {scan.status === 'completed' ? '완료' : scan.status === 'failed' ? '실패' : '진행중'}
                            </span>
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatDate(scan.started_at)}
                            {scan.execution_time_seconds > 0 && ` • ${formatDuration(scan.execution_time_seconds)}`}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-bold text-primary">{scan.total_keywords?.toLocaleString() || 0}개</p>
                        <p className="text-xs text-muted-foreground">수집 키워드</p>
                      </div>
                    </div>

                    {/* 등급별 통계 */}
                    {scan.status === 'completed' && (
                      <div className="grid grid-cols-4 gap-2 mb-3">
                        <div className="text-center p-2 bg-muted rounded">
                          <div className="text-lg font-bold text-red-500">{scan.s_grade_count || 0}</div>
                          <div className="text-xs text-muted-foreground">🔥 S급</div>
                        </div>
                        <div className="text-center p-2 bg-muted rounded">
                          <div className="text-lg font-bold text-green-500">{scan.a_grade_count || 0}</div>
                          <div className="text-xs text-muted-foreground">🟢 A급</div>
                        </div>
                        <div className="text-center p-2 bg-muted rounded">
                          <div className="text-lg font-bold text-blue-500">{scan.b_grade_count || 0}</div>
                          <div className="text-xs text-muted-foreground">🔵 B급</div>
                        </div>
                        <div className="text-center p-2 bg-muted rounded">
                          <div className="text-lg font-bold text-muted-foreground">{scan.c_grade_count || 0}</div>
                          <div className="text-xs text-muted-foreground">⚪ C급</div>
                        </div>
                      </div>
                    )}

                    {/* 에러 메시지 */}
                    {scan.status === 'failed' && scan.error_message && (
                      <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400">
                        ❌ {scan.error_message}
                      </div>
                    )}

                    {/* 상위 키워드 */}
                    {scan.topKeywords && scan.topKeywords.length > 0 && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">🔥 상위 키워드</p>
                        <div className="flex flex-wrap gap-1">
                          {scan.topKeywords.slice(0, 5).map((kw: Keyword, idx: number) => (
                            <span
                              key={idx}
                              className={`text-xs px-2 py-0.5 rounded ${
                                kw.grade === 'S'
                                  ? 'bg-red-500/10 text-red-500'
                                  : kw.grade === 'A'
                                  ? 'bg-green-500/10 text-green-500'
                                  : 'bg-muted text-muted-foreground'
                              }`}
                            >
                              {kw.keyword}
                            </span>
                          ))}
                          {scan.topKeywords.length > 5 && (
                            <span className="text-xs text-muted-foreground">
                              +{scan.topKeywords.length - 5}개 더
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 날짜별 수집 현황 뷰 */}
      {historyView === 'dates' && (
        <>
      {/* 상단 요약 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-primary">{totalStats.days}</div>
          <div className="text-sm text-muted-foreground mt-2">총 수집 일수</div>
        </div>

        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-blue-500">{totalStats.total.toLocaleString()}</div>
          <div className="text-sm text-muted-foreground mt-2">총 키워드</div>
        </div>

        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-green-500">{(totalStats.sCount + totalStats.aCount).toLocaleString()}</div>
          <div className="text-sm text-muted-foreground mt-2">총 S/A급</div>
        </div>
      </div>

      {/* 조회 범위 선택 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📅 조회 범위</h3>
        <div className="flex gap-2 mb-4">
          {[
            { value: 'recent7', label: '최근 7일' },
            { value: 'recent30', label: '최근 30일' },
            { value: 'custom', label: '날짜 선택' },
          ].map((option) => (
            <button
              key={option.value}
              onClick={() => setViewOption(option.value as any)}
              className={`
                px-4 py-2 rounded-lg font-medium transition-colors
                ${viewOption === option.value
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }
              `}
            >
              {option.label}
            </button>
          ))}
        </div>

        {viewOption === 'custom' && (
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="w-full md:w-auto px-3 py-2 bg-background border border-border rounded-md"
          >
            <option value="">날짜를 선택하세요</option>
            {dateStats.map((stat) => (
              <option key={stat.date} value={stat.date}>
                {stat.date} ({stat.total}개)
              </option>
            ))}
          </select>
        )}
      </div>

      {/* 날짜별 수집 현황 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📊 날짜별 수집 현황</h3>

        {filteredDates.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-4xl mb-4">📭</p>
            <p>선택된 기간에 데이터가 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredDates.slice(0, 10).map((stat, index: number) => {
              const saRatio = ((stat.sCount + stat.aCount) / stat.total * 100).toFixed(1)
              // 소스별 상위 정보 (향후 UI 표시용)
              const _topSources = Object.entries(stat.sources)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 3)
                .map(([name, count]) => `${name}: ${count}개`)
                .join(', ')
              void _topSources // unused variable

              return (
                <details
                  key={stat.date}
                  className="border border-border rounded-lg"
                  open={index === 0}
                >
                  <summary className="cursor-pointer px-4 py-3 hover:bg-muted transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="font-semibold">
                        📅 {stat.date}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        총 {stat.total}개 (🔥S: {stat.sCount}, 🟢A: {stat.aCount})
                      </div>
                    </div>
                  </summary>

                  <div className="px-4 py-4 border-t border-border space-y-4">
                    {/* 메트릭 */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center p-3 bg-muted rounded">
                        <div className="text-2xl font-bold">{stat.total}</div>
                        <div className="text-xs text-muted-foreground mt-1">수집 키워드</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded">
                        <div className="text-2xl font-bold text-red-500">{stat.sCount}</div>
                        <div className="text-xs text-muted-foreground mt-1">🔥 S급</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded">
                        <div className="text-2xl font-bold text-green-500">{stat.aCount}</div>
                        <div className="text-xs text-muted-foreground mt-1">🟢 A급</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded">
                        <div className="text-2xl font-bold text-blue-500">{saRatio}%</div>
                        <div className="text-xs text-muted-foreground mt-1">S/A 비율</div>
                      </div>
                    </div>

                    {/* 소스 분포 */}
                    <div>
                      <div className="text-sm font-semibold mb-2">📦 소스 분포</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(stat.sources).map(([source, count]) => (
                          <span
                            key={source}
                            className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-500"
                          >
                            {source}: {count}개
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* 카테고리 분포 */}
                    <div>
                      <div className="text-sm font-semibold mb-2">📂 카테고리 분포</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(stat.categories)
                          .sort(([, a], [, b]) => b - a)
                          .map(([category, count]) => (
                            <span
                              key={category}
                              className="text-xs px-2 py-1 rounded bg-purple-500/10 text-purple-500"
                            >
                              {category}: {count}개
                            </span>
                          ))}
                      </div>
                    </div>

                    {/* 상위 S/A급 키워드 */}
                    <div>
                      <div className="text-sm font-semibold mb-2">🔥 상위 S/A급 키워드</div>
                      <div className="space-y-1">
                        {stat.keywords
                          .filter((kw) => ['S', 'A'].includes(kw.grade))
                          .sort((a, b) => (b.search_volume || 0) - (a.search_volume || 0))
                          .slice(0, 10)
                          .map((kw, i) => (
                            <div
                              key={i}
                              className="text-sm flex items-center justify-between p-2 rounded hover:bg-muted/50"
                            >
                              <span>
                                <span className={kw.grade === 'S' ? 'text-red-500' : 'text-green-500'}>
                                  {kw.grade === 'S' ? '🔥' : '🟢'} {kw.grade}
                                </span>
                                {' '}{kw.keyword}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {kw.search_volume?.toLocaleString() || 0}
                              </span>
                            </div>
                          ))}
                      </div>
                    </div>

                    {/* 전체 데이터 테이블 (접기) */}
                    <details>
                      <summary className="cursor-pointer text-sm font-semibold text-primary hover:underline">
                        📋 전체 키워드 보기 ({stat.total}개)
                      </summary>
                      <div className="mt-2 max-h-96 overflow-y-auto">
                        <table className="w-full text-sm">
                          <thead className="sticky top-0 bg-muted">
                            <tr>
                              <th className="text-left py-2 px-2">키워드</th>
                              <th className="text-center py-2 px-2">등급</th>
                              <th className="text-right py-2 px-2">검색량</th>
                              <th className="text-left py-2 px-2">카테고리</th>
                            </tr>
                          </thead>
                          <tbody>
                            {stat.keywords.map((kw, i) => (
                              <tr key={i} className="border-t border-border">
                                <td className="py-1 px-2">{kw.keyword}</td>
                                <td className="text-center py-1 px-2">
                                  <span className={
                                    kw.grade === 'S' ? 'text-red-500' :
                                    kw.grade === 'A' ? 'text-green-500' :
                                    kw.grade === 'B' ? 'text-blue-500' : 'text-muted-foreground'
                                  }>
                                    {kw.grade}
                                  </span>
                                </td>
                                <td className="text-right py-1 px-2">{kw.search_volume?.toLocaleString() || 0}</td>
                                <td className="py-1 px-2 text-xs text-muted-foreground">{kw.category || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  </div>
                </details>
              )
            })}

            {filteredDates.length > 10 && (
              <p className="text-sm text-muted-foreground text-center">
                상위 10일만 표시됩니다. ({filteredDates.length}일 중 10일)
              </p>
            )}
          </div>
        )}
      </div>
        </>
      )}
    </div>
  )
}
