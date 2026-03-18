import { useMemo } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, Legend
} from 'recharts'

interface ViralTarget {
  id: string
  platform: string
  priority_score?: number
  discovered_at?: string
  category?: string
  comment_status?: string
  matched_keywords?: string[]
}

// [Phase 9.0] 백엔드 집계 통계 기반 props
interface StatsData {
  platform_stats: Record<string, { count: number; avgScore: number; maxScore: number }>
  category_stats: Array<{ category: string; count: number; avgScore: number; maxScore: number; priority: number }>
  status_stats: Record<string, number>
  score_distribution: Record<string, number>
}

interface ViralChartsProps {
  targets?: ViralTarget[]  // 기존 방식 (optional)
  statsData?: StatsData    // [Phase 9.0] 백엔드 집계 통계 (optional)
  compact?: boolean
}

// 플랫폼 색상 매핑
const PLATFORM_COLORS: Record<string, string> = {
  cafe: '#22c55e',      // green
  blog: '#3b82f6',      // blue
  kin: '#f59e0b',       // amber
  youtube: '#ef4444',   // red
  instagram: '#ec4899', // pink
  tiktok: '#14b8a6',    // teal
  place: '#8b5cf6',     // violet
  karrot: '#f97316',    // orange
  other: '#6b7280',     // gray
}

const PLATFORM_LABELS: Record<string, string> = {
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

// 카테고리 색상 매핑
const CATEGORY_COLORS: Record<string, string> = {
  '다이어트': '#ef4444',
  '비대칭/교정': '#f97316',
  '피부': '#eab308',
  '교통사고': '#22c55e',
  '통증/디스크': '#14b8a6',
  '두통/어지럼': '#3b82f6',
  '소화기': '#8b5cf6',
  '호흡기': '#ec4899',
  '기타': '#6b7280',
}

// 댓글 상태 색상 매핑
const STATUS_COLORS: Record<string, string> = {
  pending: '#6b7280',
  generated: '#3b82f6',
  approved: '#22c55e',
  posted: '#8b5cf6',
  skipped: '#f59e0b',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '대기중',
  generated: 'AI 생성됨',
  approved: '승인됨',
  posted: '게시됨',
  skipped: '건너뜀',
}

export function ViralCharts({ targets = [], statsData, compact = false }: ViralChartsProps) {
  // [Phase 9.0] 플랫폼별 분포 데이터 - statsData 우선 사용
  const platformData = useMemo(() => {
    // statsData가 있으면 백엔드 집계 사용
    if (statsData?.platform_stats) {
      return Object.entries(statsData.platform_stats)
        .map(([platform, stats]) => ({
          name: PLATFORM_LABELS[platform] || platform,
          value: stats.count,
          color: PLATFORM_COLORS[platform] || PLATFORM_COLORS.other,
        }))
        .sort((a, b) => b.value - a.value)
    }

    // 기존 방식: targets에서 계산
    const counts: Record<string, number> = {}
    targets.forEach(t => {
      const platform = t.platform?.toLowerCase() || 'other'
      counts[platform] = (counts[platform] || 0) + 1
    })

    return Object.entries(counts)
      .map(([name, value]) => ({
        name: PLATFORM_LABELS[name] || name,
        value,
        color: PLATFORM_COLORS[name] || PLATFORM_COLORS.other,
      }))
      .sort((a, b) => b.value - a.value)
  }, [targets, statsData])

  // 우선순위 점수 분포 (히스토그램)
  const scoreDistribution = useMemo(() => {
    const buckets = [
      { range: '0-20', min: 0, max: 20, count: 0 },
      { range: '21-40', min: 21, max: 40, count: 0 },
      { range: '41-60', min: 41, max: 60, count: 0 },
      { range: '61-80', min: 61, max: 80, count: 0 },
      { range: '81-100', min: 81, max: 100, count: 0 },
      { range: '100+', min: 101, max: 999, count: 0 },
    ]

    targets.forEach(t => {
      const score = t.priority_score || 0
      const bucket = buckets.find(b => score >= b.min && score <= b.max)
      if (bucket) bucket.count++
    })

    return buckets.map(b => ({
      range: b.range,
      count: b.count,
      fill: b.min >= 81 ? '#ef4444' : b.min >= 61 ? '#f59e0b' : b.min >= 41 ? '#22c55e' : '#6b7280'
    }))
  }, [targets])

  // 일별 발견 추이 (최근 14일)
  const dailyTrend = useMemo(() => {
    const days: Record<string, number> = {}
    const now = new Date()

    // 최근 14일 초기화
    for (let i = 13; i >= 0; i--) {
      const date = new Date(now)
      date.setDate(date.getDate() - i)
      const key = date.toISOString().split('T')[0]
      days[key] = 0
    }

    // 타겟별 날짜 집계
    targets.forEach(t => {
      if (t.discovered_at) {
        const date = t.discovered_at.split('T')[0]
        if (days.hasOwnProperty(date)) {
          days[date]++
        }
      }
    })

    return Object.entries(days).map(([date, count]) => ({
      date: `${new Date(date).getMonth() + 1}/${new Date(date).getDate()}`,
      count,
    }))
  }, [targets])

  // [Phase 9.0] 카테고리별 분포 데이터 - statsData 우선 사용
  const categoryData = useMemo(() => {
    // statsData가 있으면 백엔드 집계 사용
    if (statsData?.category_stats) {
      return statsData.category_stats
        .map(cat => ({
          name: cat.category,
          value: cat.count,
          color: CATEGORY_COLORS[cat.category] || CATEGORY_COLORS['기타'],
        }))
        .sort((a, b) => b.value - a.value)
    }

    // 기존 방식: targets에서 계산
    const counts: Record<string, number> = {}
    targets.forEach(t => {
      const category = t.category || '기타'
      counts[category] = (counts[category] || 0) + 1
    })

    return Object.entries(counts)
      .map(([name, value]) => ({
        name,
        value,
        color: CATEGORY_COLORS[name] || CATEGORY_COLORS['기타'],
      }))
      .sort((a, b) => b.value - a.value)
  }, [targets, statsData])

  // [Phase 9.0] 댓글 상태별 분포 데이터 - statsData 우선 사용
  const statusData = useMemo(() => {
    // statsData가 있으면 백엔드 집계 사용
    if (statsData?.status_stats) {
      return Object.entries(statsData.status_stats)
        .map(([status, value]) => ({
          name: STATUS_LABELS[status] || status,
          status,
          value,
          color: STATUS_COLORS[status] || STATUS_COLORS.pending,
        }))
        .sort((a, b) => b.value - a.value)
    }

    // 기존 방식: targets에서 계산
    const counts: Record<string, number> = {}
    targets.forEach(t => {
      const status = t.comment_status || 'pending'
      counts[status] = (counts[status] || 0) + 1
    })

    return Object.entries(counts)
      .map(([status, value]) => ({
        name: STATUS_LABELS[status] || status,
        status,
        value,
        color: STATUS_COLORS[status] || STATUS_COLORS.pending,
      }))
      .sort((a, b) => b.value - a.value)
  }, [targets, statsData])

  // 플랫폼별 평균 점수 데이터
  const platformScoreData = useMemo(() => {
    const platformStats: Record<string, { total: number; count: number }> = {}

    targets.forEach(t => {
      const platform = t.platform?.toLowerCase() || 'other'
      const score = t.priority_score || 0

      if (!platformStats[platform]) {
        platformStats[platform] = { total: 0, count: 0 }
      }
      platformStats[platform].total += score
      platformStats[platform].count++
    })

    return Object.entries(platformStats)
      .map(([platform, stats]) => ({
        name: PLATFORM_LABELS[platform] || platform,
        avgScore: Math.round(stats.total / stats.count),
        count: stats.count,
        color: PLATFORM_COLORS[platform] || PLATFORM_COLORS.other,
      }))
      .sort((a, b) => b.avgScore - a.avgScore)
  }, [targets])

  // [Phase 9.0] 데이터 없음 체크 - statsData 또는 targets 중 하나라도 있으면 OK
  const hasData = (statsData && Object.keys(statsData.platform_stats || {}).length > 0) || targets.length > 0
  if (!hasData) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center text-muted-foreground">
        시각화할 데이터가 없습니다.
      </div>
    )
  }

  // 간결 모드 (홈 화면용) - 3개 차트 그리드
  if (compact) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 플랫폼별 분포 */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            📊 플랫폼별
          </h3>
          <div className="flex items-center gap-3">
            <div className="w-20 h-20">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformData}
                    cx="50%"
                    cy="50%"
                    innerRadius={18}
                    outerRadius={35}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {platformData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-1">
              {platformData.slice(0, 4).map((p) => (
                <div key={p.name} className="flex items-center gap-1.5 text-xs">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: p.color }}
                  />
                  <span className="text-muted-foreground truncate">{p.name}</span>
                  <span className="font-medium ml-auto">{p.value}</span>
                </div>
              ))}
              {platformData.length > 4 && (
                <div className="text-xs text-muted-foreground">
                  +{platformData.length - 4}개 더
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 카테고리별 분포 */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            🏷️ 카테고리별
          </h3>
          <div className="flex items-center gap-3">
            <div className="w-20 h-20">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={18}
                    outerRadius={35}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-1">
              {categoryData.slice(0, 4).map((c) => (
                <div key={c.name} className="flex items-center gap-1.5 text-xs">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: c.color }}
                  />
                  <span className="text-muted-foreground truncate">{c.name}</span>
                  <span className="font-medium ml-auto">{c.value}</span>
                </div>
              ))}
              {categoryData.length > 4 && (
                <div className="text-xs text-muted-foreground">
                  +{categoryData.length - 4}개 더
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 댓글 상태별 분포 */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            📝 작업 현황
          </h3>
          <div className="flex items-center gap-3">
            <div className="w-20 h-20">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusData}
                    cx="50%"
                    cy="50%"
                    innerRadius={18}
                    outerRadius={35}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {statusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-1">
              {statusData.map((s) => (
                <div key={s.status} className="flex items-center gap-1.5 text-xs">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: s.color }}
                  />
                  <span className="text-muted-foreground truncate">{s.name}</span>
                  <span className="font-medium ml-auto">{s.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 플랫폼별 분포 파이차트 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📊 플랫폼별 분포</h3>
          <div className="flex items-center gap-6">
            <div className="w-48 h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {platformData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => [`${value}개`, '타겟 수']}
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2">
              {platformData.map((p) => (
                <div key={p.name} className="flex items-center gap-3">
                  <div
                    className="w-4 h-4 rounded"
                    style={{ backgroundColor: p.color }}
                  />
                  <span className="text-sm">{p.name}</span>
                  <span className="font-bold ml-auto">{p.value}개</span>
                  <span className="text-xs text-muted-foreground w-12 text-right">
                    {((p.value / targets.length) * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 우선순위 점수 분포 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">🎯 우선순위 점수 분포</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={scoreDistribution} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="range"
                  tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                />
                <Tooltip
                  formatter={(value: number) => [`${value}개`, '타겟 수']}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {scoreDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 mt-4 text-xs">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-gray-500" />
              <span>낮음 (0-40)</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-green-500" />
              <span>중간 (41-60)</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-amber-500" />
              <span>높음 (61-80)</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-red-500" />
              <span>최우선 (81+)</span>
            </div>
          </div>
        </div>
      </div>

      {/* 일별 발견 추이 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">📈 일별 발견 추이 (최근 14일)</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={dailyTrend} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={{ stroke: 'hsl(var(--border))' }}
              />
              <YAxis
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={{ stroke: 'hsl(var(--border))' }}
              />
              <Tooltip
                formatter={(value: number) => [`${value}개`, '발견된 타겟']}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="count"
                name="발견 수"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ fill: '#3b82f6', strokeWidth: 0, r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 카테고리별 분포 & 댓글 상태별 분포 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 카테고리별 분포 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">🏷️ 카테고리별 분포</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={categoryData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  type="number"
                  tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  width={55}
                />
                <Tooltip
                  formatter={(value: number) => [`${value}개`, '타겟 수']}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {categoryData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 댓글 상태별 분포 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📝 댓글 상태별 분포</h3>
          <div className="flex items-center gap-6">
            <div className="w-48 h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {statusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => [`${value}개`, '타겟 수']}
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-3">
              {statusData.map((s) => (
                <div key={s.status} className="flex items-center gap-3">
                  <div
                    className="w-4 h-4 rounded"
                    style={{ backgroundColor: s.color }}
                  />
                  <span className="text-sm">{s.name}</span>
                  <span className="font-bold ml-auto">{s.value}개</span>
                  <span className="text-xs text-muted-foreground w-12 text-right">
                    {((s.value / targets.length) * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 플랫폼별 평균 점수 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">⭐ 플랫폼별 평균 우선순위 점수</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={platformScoreData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={{ stroke: 'hsl(var(--border))' }}
              />
              <YAxis
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={{ stroke: 'hsl(var(--border))' }}
                domain={[0, 'auto']}
              />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name === '평균 점수') return [`${value}점`, name]
                  return [`${value}개`, name]
                }}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Legend />
              <Bar
                dataKey="avgScore"
                name="평균 점수"
                radius={[4, 4, 0, 0]}
              >
                {platformScoreData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex flex-wrap gap-4 justify-center text-xs text-muted-foreground">
          {platformScoreData.map((p) => (
            <div key={p.name} className="flex items-center gap-1">
              <div className="w-3 h-3 rounded" style={{ backgroundColor: p.color }} />
              <span>{p.name}: {p.count}개</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
