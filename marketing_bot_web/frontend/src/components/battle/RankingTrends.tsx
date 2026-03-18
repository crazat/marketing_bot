import { useState, useMemo, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import Button from '@/components/ui/Button'

// 순위 히스토리 항목 타입
interface RankHistoryItem {
  date: string
  rank: number
  device_type?: string
}

// 디바이스별 히스토리
interface DeviceHistory {
  mobile: RankHistoryItem[]
  desktop: RankHistoryItem[]
}

// 트렌드 API 응답 타입
interface TrendsSummary {
  total: number
  improving: number
  declining: number
  stable: number
}

interface TrendsData {
  keywords: Record<string, DeviceHistory | RankHistoryItem[]>  // 구버전 호환
  summary?: TrendsSummary
}

// 랭킹 키워드 항목 타입
interface RankingKeywordItem {
  keyword: string
  current_rank: number
  mobile_rank?: number      // 모바일 순위
  desktop_rank?: number     // 데스크톱 순위
  rank_change: number
  target_rank?: number
  category?: string
  search_volume?: number
  status?: string
}

// 차트 데이터 포인트 타입
interface ChartDataPoint {
  date: string
  displayDate: string
  [keyword: string]: string | number  // 동적 키워드 필드
}

interface RankingTrendsProps {
  trends: TrendsData | null
  rankingKeywords?: RankingKeywordItem[]  // 현재 순위 데이터 (ranking-keywords API에서)
}

// 색상 팔레트
const COLORS = [
  '#22c55e', // green
  '#3b82f6', // blue
  '#f59e0b', // amber
  '#ec4899', // pink
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#f97316', // orange
  '#84cc16', // lime
  '#6366f1', // indigo
]

export default function RankingTrends({ trends, rankingKeywords }: RankingTrendsProps) {
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([])
  const [viewMode, setViewMode] = useState<'chart' | 'cards'>('chart')
  const [showDataTable, setShowDataTable] = useState(false)

  // rankingKeywords를 맵으로 변환 (현재 순위 빠른 조회용)
  const currentRankMap = useMemo(() => {
    const map: Record<string, {
      rank: number
      change: number
      mobile_rank: number
      desktop_rank: number
    }> = {}
    if (rankingKeywords) {
      rankingKeywords.forEach((kw: RankingKeywordItem) => {
        map[kw.keyword] = {
          rank: kw.current_rank || 0,
          change: kw.rank_change || 0,
          mobile_rank: kw.mobile_rank || 0,
          desktop_rank: kw.desktop_rank || 0
        }
      })
    }
    return map
  }, [rankingKeywords])

  // 키워드 목록 및 분석 데이터 추출
  const keywordsData = useMemo(() => {
    if (!trends || !trends.keywords) return []

    return Object.entries(trends.keywords).map(([keyword, historyData]) => {
      // 새 형식 (DeviceHistory) vs 구 형식 (RankHistoryItem[]) 처리
      let mobileHistory: RankHistoryItem[] = []
      let desktopHistory: RankHistoryItem[] = []

      if (Array.isArray(historyData)) {
        // 구 형식: 모든 데이터를 모바일로 취급
        mobileHistory = historyData
      } else {
        // 새 형식: DeviceHistory
        mobileHistory = historyData.mobile || []
        desktopHistory = historyData.desktop || []
      }

      // 모바일 우선, 없으면 데스크톱 사용
      const primaryHistory = mobileHistory.length > 0 ? mobileHistory : desktopHistory
      const sortedHistory = [...primaryHistory].sort((a, b) =>
        new Date(a.date).getTime() - new Date(b.date).getTime()
      )

      // 모바일/데스크톱 개별 순위 (API에서)
      const mobileRank = currentRankMap[keyword]?.mobile_rank || 0
      const desktopRank = currentRankMap[keyword]?.desktop_rank || 0

      // 현재 순위: 히스토리의 마지막 값 사용 (차트와 일관성 유지)
      const historyLastRank = sortedHistory.length > 0 ? sortedHistory[sortedHistory.length - 1].rank : 0
      const rankingApiRank = currentRankMap[keyword]?.rank || 0

      // 차트와 동일한 소스(히스토리)의 마지막 순위 사용
      const actualCurrentRank = historyLastRank > 0 ? historyLastRank : rankingApiRank

      // 기간 내 트렌드 계산 (선택한 기간 동안의 변화)
      let periodTrend = 'stable'
      let periodRankChange = 0
      if (sortedHistory.length >= 2) {
        const firstRank = sortedHistory[0].rank
        const lastRank = sortedHistory[sortedHistory.length - 1].rank
        periodRankChange = firstRank - lastRank // 양수면 순위 상승

        if (periodRankChange > 2) periodTrend = 'improving'
        else if (periodRankChange < -2) periodTrend = 'declining'
      }

      // 최근 변화: rankingKeywords에서 가져오기 (어제 대비 변화)
      const recentRankChange = currentRankMap[keyword]?.change || 0

      const ranks = sortedHistory.map(h => h.rank).filter(r => r > 0)
      const bestRank = ranks.length > 0 ? Math.min(...ranks) : actualCurrentRank
      const worstRank = ranks.length > 0 ? Math.max(...ranks) : actualCurrentRank
      const avgRank = ranks.length > 0 ? ranks.reduce((a, b) => a + b, 0) / ranks.length : actualCurrentRank

      // [Phase 8.0] 연속 상승/하락 일수 계산
      let consecutiveDays = 0
      let consecutiveDirection: 'up' | 'down' | 'stable' = 'stable'
      if (sortedHistory.length >= 2) {
        for (let i = sortedHistory.length - 1; i > 0; i--) {
          const currentRank = sortedHistory[i].rank
          const prevRank = sortedHistory[i - 1].rank
          if (currentRank < prevRank) {
            // 순위 상승 (숫자가 낮을수록 높은 순위)
            if (consecutiveDirection === 'stable') consecutiveDirection = 'up'
            if (consecutiveDirection === 'up') {
              consecutiveDays++
            } else {
              break
            }
          } else if (currentRank > prevRank) {
            // 순위 하락
            if (consecutiveDirection === 'stable') consecutiveDirection = 'down'
            if (consecutiveDirection === 'down') {
              consecutiveDays++
            } else {
              break
            }
          } else {
            break
          }
        }
      }

      // [Phase 8.0] 변화율 계산 (기간 시작 대비 %)
      let changeRate = 0
      if (sortedHistory.length >= 2) {
        const firstRank = sortedHistory[0].rank
        const lastRank = sortedHistory[sortedHistory.length - 1].rank
        if (firstRank > 0) {
          changeRate = ((firstRank - lastRank) / firstRank) * 100
        }
      }

      return {
        keyword,
        history: sortedHistory,
        mobileHistory,                      // 모바일 히스토리
        desktopHistory,                     // 데스크톱 히스토리
        trend: periodTrend,
        rankChange: periodRankChange,      // 선택한 기간 동안의 변화
        recentRankChange,                   // 최근(어제 대비) 변화
        currentRank: actualCurrentRank,     // 실제 현재 순위 (ranking-keywords에서)
        mobileRank,                         // 모바일 순위
        desktopRank,                        // 데스크톱 순위
        bestRank,
        worstRank,
        avgRank,
        consecutiveDays,                    // 연속 상승/하락 일수
        consecutiveDirection,               // 연속 방향
        changeRate,                         // 변화율 (%)
      }
    })
  }, [trends, currentRankMap])

  // 차트 데이터 변환
  const chartData = useMemo(() => {
    if (!trends || !trends.keywords) return []

    // 모든 날짜 수집 (모바일 기준)
    const allDates = new Set<string>()
    Object.values(trends.keywords).forEach((historyData) => {
      // 새 형식 (DeviceHistory) vs 구 형식 (RankHistoryItem[]) 처리
      let historyArray: RankHistoryItem[] = []
      if (Array.isArray(historyData)) {
        historyArray = historyData
      } else {
        // 모바일 우선, 없으면 데스크톱
        historyArray = historyData.mobile?.length > 0 ? historyData.mobile : (historyData.desktop || [])
      }

      historyArray.forEach((h: RankHistoryItem) => {
        const date = h.date?.split('T')[0] || h.date
        if (date) allDates.add(date)
      })
    })

    // 날짜별 데이터 구성
    const sortedDates = Array.from(allDates).sort()
    return sortedDates.map(date => {
      const point: ChartDataPoint = {
        date,
        displayDate: new Date(date).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
      }

      Object.entries(trends.keywords).forEach(([keyword, historyData]) => {
        // 새 형식 (DeviceHistory) vs 구 형식 (RankHistoryItem[]) 처리
        let historyArray: RankHistoryItem[] = []
        if (Array.isArray(historyData)) {
          historyArray = historyData
        } else {
          // 모바일 우선, 없으면 데스크톱
          historyArray = historyData.mobile?.length > 0 ? historyData.mobile : (historyData.desktop || [])
        }

        const historyItem = historyArray.find((h: RankHistoryItem) => {
          const hDate = h.date?.split('T')[0] || h.date
          return hDate === date
        })
        if (historyItem && historyItem.rank > 0) {
          point[keyword] = historyItem.rank
        }
      })

      return point
    })
  }, [trends])

  // 선택된 키워드 또는 전체 (최대 9개)
  const displayKeywords = useMemo(() => {
    if (selectedKeywords.length > 0) {
      return selectedKeywords
    }
    return keywordsData.slice(0, 9).map(k => k.keyword)
  }, [keywordsData, selectedKeywords])

  const toggleKeyword = (keyword: string) => {
    setSelectedKeywords(prev => {
      if (prev.includes(keyword)) {
        return prev.filter(k => k !== keyword)
      }
      if (prev.length >= 9) return prev // 최대 9개
      return [...prev, keyword]
    })
  }

  // [Phase 4-2] 차트 대체 텍스트 생성
  const generateChartDescription = useCallback(() => {
    const displayedData = keywordsData.filter(k => displayKeywords.includes(k.keyword))
    if (displayedData.length === 0) return '표시할 데이터가 없습니다.'

    const descriptions = displayedData.map(kw => {
      const trendText = kw.trend === 'improving' ? '상승 중' :
                        kw.trend === 'declining' ? '하락 중' : '유지 중'
      return `${kw.keyword}: 현재 ${kw.currentRank > 0 ? kw.currentRank + '위' : '순위 없음'}, ${trendText}`
    })

    const improvingCount = displayedData.filter(k => k.trend === 'improving').length
    const decliningCount = displayedData.filter(k => k.trend === 'declining').length

    return `키워드 순위 추이 차트. ${displayedData.length}개 키워드 표시 중. ` +
           `상승 ${improvingCount}개, 하락 ${decliningCount}개. ` +
           `상세: ${descriptions.join('; ')}`
  }, [keywordsData, displayKeywords])

  if (!trends || !trends.keywords || Object.keys(trends.keywords).length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-4xl mb-4">📊</p>
        <p>트렌드 데이터가 없습니다.</p>
        <p className="text-sm mt-2">순위 스캔을 실행하여 데이터를 수집하세요.</p>
      </div>
    )
  }

  const summary = trends.summary

  return (
    <div className="space-y-6">
      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground mb-1">총 키워드</div>
          <div className="text-2xl font-bold">{summary?.total || keywordsData.length}</div>
        </div>
        <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30">
          <div className="text-sm text-green-500 mb-1">📈 상승</div>
          <div className="text-2xl font-bold text-green-500">{summary?.improving || 0}</div>
        </div>
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30">
          <div className="text-sm text-red-500 mb-1">📉 하락</div>
          <div className="text-2xl font-bold text-red-500">{summary?.declining || 0}</div>
        </div>
        <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/30">
          <div className="text-sm text-blue-500 mb-1">➡️ 유지</div>
          <div className="text-2xl font-bold text-blue-500">{summary?.stable || 0}</div>
        </div>
        {/* 연속 상승/하락 통계 */}
        <div className="p-4 rounded-lg bg-orange-500/10 border border-orange-500/30">
          <div className="text-sm text-orange-500 mb-1">🔥 연속 상승</div>
          <div className="text-2xl font-bold text-orange-500">
            {keywordsData.filter(k => k.consecutiveDirection === 'up' && k.consecutiveDays >= 2).length}
          </div>
        </div>
        <div className="p-4 rounded-lg bg-purple-500/10 border border-purple-500/30">
          <div className="text-sm text-purple-500 mb-1">⚠️ 연속 하락</div>
          <div className="text-2xl font-bold text-purple-500">
            {keywordsData.filter(k => k.consecutiveDirection === 'down' && k.consecutiveDays >= 2).length}
          </div>
        </div>
      </div>

      {/* 뷰 모드 토글 */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('chart')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'chart'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            📈 차트 뷰
          </button>
          <button
            onClick={() => setViewMode('cards')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'cards'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            📋 카드 뷰
          </button>
        </div>

        {viewMode === 'chart' && selectedKeywords.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedKeywords([])}
          >
            전체 보기
          </Button>
        )}
      </div>

      {/* 키워드 선택 칩 */}
      {viewMode === 'chart' && (
        <div className="flex flex-wrap gap-2">
          {keywordsData.map((kw, index) => {
            const isSelected = selectedKeywords.length === 0
              ? index < 9
              : selectedKeywords.includes(kw.keyword)
            const color = COLORS[index % COLORS.length]

            return (
              <button
                key={kw.keyword}
                onClick={() => toggleKeyword(kw.keyword)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  isSelected
                    ? 'text-white'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
                style={isSelected ? { backgroundColor: color } : undefined}
              >
                {kw.trend === 'improving' ? '📈' :
                 kw.trend === 'declining' ? '📉' : '➡️'} {kw.keyword}
              </button>
            )
          })}
        </div>
      )}

      {/* 차트 뷰 */}
      {viewMode === 'chart' && chartData.length > 0 && (
        <div className="bg-card rounded-lg border border-border p-4">
          {/* 접근성: 차트 대체 텍스트 */}
          <div
            role="img"
            aria-label={generateChartDescription()}
            className="focus:outline-none focus:ring-2 focus:ring-primary rounded-lg"
            tabIndex={0}
          >
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="displayDate"
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={12}
                />
                <YAxis
                  reversed
                  domain={[1, 'auto']}
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={12}
                  label={{
                    value: '순위',
                    angle: -90,
                    position: 'insideLeft',
                    style: { fill: 'hsl(var(--muted-foreground))' }
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: 'hsl(var(--foreground))' }}
                  formatter={(value: number) => [`#${value}`, '']}
                />
                <Legend />
                {displayKeywords.map((keyword, index) => (
                  <Line
                    key={keyword}
                    type="monotone"
                    dataKey={keyword}
                    stroke={COLORS[index % COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-muted-foreground">
              * 순위가 낮을수록 상위 노출 (1위가 가장 좋음)
            </p>
            {/* 접근성: 데이터 테이블로 보기 옵션 */}
            <button
              onClick={() => setShowDataTable(!showDataTable)}
              className="text-xs text-primary hover:underline"
              aria-expanded={showDataTable}
            >
              {showDataTable ? '테이블 숨기기' : '📊 데이터 테이블로 보기'}
            </button>
          </div>
          {/* 접근성: 데이터 테이블 */}
          {showDataTable && (
            <details open className="mt-4">
              <summary className="sr-only">키워드 순위 데이터 테이블</summary>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left p-2 font-semibold">날짜</th>
                      {displayKeywords.map(kw => (
                        <th key={kw} className="text-right p-2 font-semibold">{kw}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((row) => (
                      <tr key={row.date} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="p-2">{row.displayDate}</td>
                        {displayKeywords.map(kw => (
                          <td key={kw} className="text-right p-2">
                            {row[kw] ? `#${row[kw]}` : '-'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}

      {viewMode === 'chart' && chartData.length === 0 && (
        <div className="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
          <p>차트를 표시할 데이터가 충분하지 않습니다.</p>
        </div>
      )}

      {/* 카드 뷰 */}
      {viewMode === 'cards' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {keywordsData.map((kw, index) => {
            const color = COLORS[index % COLORS.length]

            return (
              <div
                key={kw.keyword}
                className="p-4 rounded-lg border border-border bg-card hover:shadow-lg transition-shadow"
              >
                <div className="flex items-start justify-between mb-3">
                  <h4 className="font-semibold truncate flex-1 mr-2">{kw.keyword}</h4>
                  <span
                    className="text-xs px-2 py-1 rounded-full text-white"
                    style={{ backgroundColor: color }}
                  >
                    {kw.trend === 'improving' ? '📈 상승' :
                     kw.trend === 'declining' ? '📉 하락' : '➡️ 유지'}
                  </span>
                </div>

                {/* 모바일/데스크톱 순위 표시 */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  {/* 모바일 순위 */}
                  <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                    <div className="flex items-center gap-1.5 text-xs text-blue-400 mb-1">
                      <span>📱</span>
                      <span>모바일</span>
                    </div>
                    <div className="text-2xl font-bold text-blue-400">
                      {kw.mobileRank > 0 ? `#${kw.mobileRank}` : '-'}
                    </div>
                  </div>
                  {/* 데스크톱 순위 */}
                  <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
                    <div className="flex items-center gap-1.5 text-xs text-purple-400 mb-1">
                      <span>🖥️</span>
                      <span>데스크톱</span>
                    </div>
                    <div className="text-2xl font-bold text-purple-400">
                      {kw.desktopRank > 0 ? `#${kw.desktopRank}` : '-'}
                    </div>
                  </div>
                </div>

                {/* 순위 차이 표시 (모바일 vs 데스크톱) */}
                {kw.mobileRank > 0 && kw.desktopRank > 0 && kw.mobileRank !== kw.desktopRank && (
                  <div className={`text-xs px-2 py-1 rounded mb-3 ${
                    kw.mobileRank < kw.desktopRank
                      ? 'bg-blue-500/10 text-blue-400'
                      : 'bg-purple-500/10 text-purple-400'
                  }`}>
                    {kw.mobileRank < kw.desktopRank
                      ? `📱 모바일이 ${kw.desktopRank - kw.mobileRank}순위 더 높음`
                      : `🖥️ 데스크톱이 ${kw.mobileRank - kw.desktopRank}순위 더 높음`
                    }
                  </div>
                )}

                <div className="flex items-end justify-between mb-4">
                  <div>
                    <div className="text-sm text-muted-foreground mb-1">대표 순위</div>
                    <div className="text-3xl font-bold">
                      {kw.currentRank > 0 ? `#${kw.currentRank}` : '-'}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-muted-foreground mb-1">
                      최근 변화
                      <span className="text-xs opacity-70 ml-1">(vs 어제)</span>
                    </div>
                    <div className={`text-xl font-semibold ${
                      kw.recentRankChange > 0 ? 'text-green-500' :
                      kw.recentRankChange < 0 ? 'text-red-500' : 'text-blue-500'
                    }`}>
                      {kw.recentRankChange > 0 ? `+${kw.recentRankChange}` :
                       kw.recentRankChange === 0 ? '-' : kw.recentRankChange}
                    </div>
                  </div>
                </div>

                {/* 연속성 배지 및 변화율 */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {/* 연속 상승/하락 배지 */}
                  {kw.consecutiveDays >= 2 && (
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      kw.consecutiveDirection === 'up'
                        ? 'bg-green-500/20 text-green-500'
                        : 'bg-red-500/20 text-red-500'
                    }`}>
                      {kw.consecutiveDirection === 'up' ? '🔥' : '⚠️'}
                      {kw.consecutiveDays}일 연속 {kw.consecutiveDirection === 'up' ? '상승' : '하락'}
                    </span>
                  )}

                  {/* 변화율 배지 */}
                  {Math.abs(kw.changeRate) >= 5 && (
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      kw.changeRate > 0
                        ? 'bg-green-500/10 text-green-500 border border-green-500/30'
                        : 'bg-red-500/10 text-red-500 border border-red-500/30'
                    }`}>
                      {kw.changeRate > 0 ? '↑' : '↓'}
                      {Math.abs(kw.changeRate).toFixed(1)}%
                    </span>
                  )}
                </div>

                {/* 기간별 변화 */}
                {kw.rankChange !== 0 && (
                  <div className="mb-3 p-2 rounded bg-muted/50">
                    <div className="text-xs text-muted-foreground">
                      선택 기간 내 변화:
                      <span className={`ml-1 font-semibold ${
                        kw.rankChange > 0 ? 'text-green-500' :
                        kw.rankChange < 0 ? 'text-red-500' : ''
                      }`}>
                        {kw.rankChange > 0 ? `+${kw.rankChange}` : kw.rankChange}
                      </span>
                      {Math.abs(kw.changeRate) >= 1 && (
                        <span className="ml-1 opacity-70">
                          ({kw.changeRate > 0 ? '+' : ''}{kw.changeRate.toFixed(1)}%)
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* 미니 트렌드 차트 */}
                {kw.history.length > 1 && (
                  <div
                    className="h-16"
                    role="img"
                    aria-label={`${kw.keyword} 최근 7일 순위 추이: ${kw.trend === 'improving' ? '상승 중' : kw.trend === 'declining' ? '하락 중' : '유지 중'}, 현재 ${kw.currentRank > 0 ? kw.currentRank + '위' : '순위 없음'}`}
                  >
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={kw.history.slice(-7).map((h: RankHistoryItem) => ({
                          date: new Date(h.date).toLocaleDateString('ko-KR', { day: 'numeric' }),
                          rank: h.rank
                        }))}
                      >
                        <Line
                          type="monotone"
                          dataKey="rank"
                          stroke={color}
                          strokeWidth={2}
                          dot={false}
                        />
                        <YAxis
                          reversed
                          domain={[
                            (dataMin: number) => Math.max(1, dataMin - 2),
                            (dataMax: number) => dataMax + 2
                          ]}
                          hide
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* 히스토리 요약 */}
                <div className="mt-3 pt-3 border-t border-border">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>최고: {kw.bestRank > 0 ? `#${kw.bestRank}` : '-'}</span>
                    <span>최저: {kw.worstRank > 0 ? `#${kw.worstRank}` : '-'}</span>
                    <span>평균: {kw.avgRank > 0 ? `#${kw.avgRank.toFixed(1)}` : '-'}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
