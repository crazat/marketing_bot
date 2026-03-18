import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { pathfinderApi } from '@/services/api'
import { VirtualTable } from '@/components/ui/VirtualTable'
import Button from '@/components/ui/Button'
import { Download } from 'lucide-react'
import type { Keyword, PathfinderStats } from '@/types'
import { GRADE_ICONS, GRADE_COLORS, TREND_ICONS } from '@/types'

interface KeywordAnalysisTabProps {
  stats: PathfinderStats | null
}

export default function KeywordAnalysisTab({ stats }: KeywordAnalysisTabProps) {
  const [filters, setFilters] = useState({
    grades: [] as string[],  // 빈 배열 = 전체 표시
    category: '',
    minVolume: 0,  // 0 = 전체 표시
  })

  // 모든 키워드 조회 (필터링 전)
  const { data: allKeywords, isLoading, isError } = useQuery({
    queryKey: ['pathfinder-all-keywords'],
    queryFn: () => pathfinderApi.getKeywords({
      limit: 10000, // 전체 조회
    }),
    retry: 1,  // 1회만 재시도
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 필터링된 키워드 계산
  const filteredKeywords = useMemo(() => {
    if (!allKeywords) return []

    return allKeywords.filter((kw: Keyword) => {
      // 등급 필터
      if (filters.grades.length > 0 && !filters.grades.includes(kw.grade)) {
        return false
      }

      // 카테고리 필터
      if (filters.category && kw.category !== filters.category) {
        return false
      }

      // 검색량 필터
      if (kw.search_volume < filters.minVolume) {
        return false
      }

      return true
    })
  }, [allKeywords, filters])

  // 메트릭 계산
  const metrics = useMemo(() => {
    if (!filteredKeywords || filteredKeywords.length === 0) {
      return {
        total: 0,
        avgVolume: 0,
        avgKei: 0,
        sRatio: 0,
      }
    }

    const totalVolume = filteredKeywords.reduce((sum: number, kw: Keyword) => sum + (kw.search_volume || 0), 0)
    const totalKei = filteredKeywords.reduce((sum: number, kw: Keyword) => sum + (kw.kei || 0), 0)
    const sCount = filteredKeywords.filter((kw: Keyword) => kw.grade === 'S').length

    return {
      total: filteredKeywords.length,
      avgVolume: Math.round(totalVolume / filteredKeywords.length),
      avgKei: Number((totalKei / filteredKeywords.length).toFixed(1)),
      sRatio: Number(((sCount / filteredKeywords.length) * 100).toFixed(1)),
    }
  }, [filteredKeywords])

  // CSV 다운로드
  const handleDownloadCsv = () => {
    if (!filteredKeywords || filteredKeywords.length === 0) {
      alert('다운로드할 키워드가 없습니다.')
      return
    }

    const headers = ['키워드', '등급', '검색량', '경쟁도', 'KEI', '난이도', '기회', '카테고리', '소스', '트렌드']
    const rows = filteredKeywords.map((kw: Keyword) => [
      kw.keyword,
      kw.grade,
      kw.search_volume || 0,
      kw.competition || 0,
      kw.kei || 0,
      kw.difficulty || 0,
      kw.opportunity || 0,
      kw.category || '',
      kw.source || '',
      kw.trend_status || '',
    ])

    const csv = [headers, ...rows]
      .map(row => row.map((cell: string | number) => `"${cell}"`).join(','))
      .join('\n')

    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `keywords_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
  }

  // 등급 필터 토글
  const toggleGrade = (grade: string) => {
    setFilters(prev => ({
      ...prev,
      grades: prev.grades.includes(grade)
        ? prev.grades.filter(g => g !== grade)
        : [...prev.grades, grade],
    }))
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

  // 에러 또는 데이터 없음 처리
  if (isError || !allKeywords) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="text-center py-12">
          <p className="text-4xl mb-4">🎯</p>
          <p className="text-xl font-semibold mb-2">키워드 데이터가 없습니다</p>
          <p className="text-muted-foreground mb-6">
            Pathfinder를 실행하여 키워드를 수집하세요.
          </p>
          <div className="bg-muted rounded-lg p-4 max-w-md mx-auto text-left">
            <p className="text-sm font-medium mb-2">터미널에서 실행:</p>
            <pre className="bg-background p-2 rounded text-xs overflow-x-auto">
              python pathfinder_v3_legion.py --target 500 --save-db
            </pre>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 필터 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">🔍 필터</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 등급 필터 (다중 선택) */}
          <div>
            <label className="block text-sm font-medium mb-2">등급 (다중 선택)</label>
            <div className="flex flex-wrap gap-2">
              {['S', 'A', 'B', 'C'].map((grade) => {
                const isSelected = filters.grades.includes(grade)
                return (
                  <button
                    key={grade}
                    onClick={() => toggleGrade(grade)}
                    className={`
                      px-4 py-2 rounded-lg font-medium transition-all
                      ${isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80'
                      }
                    `}
                  >
                    {GRADE_ICONS[grade]} {grade}급
                  </button>
                )
              })}
            </div>
          </div>

          {/* 카테고리 필터 */}
          <div>
            <label className="block text-sm font-medium mb-2">카테고리</label>
            <select
              value={filters.category}
              onChange={(e) => setFilters({ ...filters, category: e.target.value })}
              className="w-full px-3 py-2 bg-background border border-border rounded-md"
            >
              <option value="">전체</option>
              {stats?.categories && Object.keys(stats.categories).map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          {/* 최소 검색량 */}
          <div>
            <label className="block text-sm font-medium mb-2">최소 검색량</label>
            <input
              type="number"
              value={filters.minVolume}
              onChange={(e) => setFilters({ ...filters, minVolume: Number(e.target.value) })}
              min="0"
              step="10"
              className="w-full px-3 py-2 bg-background border border-border rounded-md"
            />
          </div>
        </div>
      </div>

      {/* 메트릭 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-primary">{metrics.total.toLocaleString()}</div>
          <div className="text-sm text-muted-foreground mt-2">필터된 키워드</div>
        </div>

        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-blue-500">{metrics.avgVolume.toLocaleString()}</div>
          <div className="text-sm text-muted-foreground mt-2">평균 검색량</div>
        </div>

        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-green-500">{metrics.avgKei}</div>
          <div className="text-sm text-muted-foreground mt-2">평균 KEI</div>
        </div>

        <div className="bg-card rounded-lg border border-border p-6 text-center">
          <div className="text-4xl font-bold text-red-500">{metrics.sRatio}%</div>
          <div className="text-sm text-muted-foreground mt-2">S급 비율</div>
        </div>
      </div>

      {/* 키워드 테이블 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">📋 키워드 목록</h3>
          <Button
            variant="success"
            size="sm"
            onClick={handleDownloadCsv}
            disabled={filteredKeywords.length === 0}
            icon={<Download size={14} />}
          >
            CSV 다운로드
          </Button>
        </div>

        <VirtualTable
          data={filteredKeywords}
          maxHeight={600}
          rowHeight={48}
          emptyMessage="필터 조건에 맞는 키워드가 없습니다."
          columns={[
            {
              key: 'keyword',
              header: '키워드',
              width: '200px',
              align: 'left',
              render: (kw: Keyword) => <span className="font-medium">{kw.keyword}</span>,
            },
            {
              key: 'grade',
              header: '등급',
              width: '80px',
              align: 'center',
              render: (kw: Keyword) => (
                <span className={`font-bold ${GRADE_COLORS[kw.grade] || ''}`}>
                  {GRADE_ICONS[kw.grade] || ''} {kw.grade}
                </span>
              ),
            },
            {
              key: 'search_volume',
              header: '검색량',
              width: '100px',
              align: 'right',
              render: (kw: Keyword) => Number(kw.search_volume || 0).toLocaleString(),
            },
            {
              key: 'competition',
              header: '경쟁도',
              width: '80px',
              align: 'right',
              render: (kw: Keyword) => Number(kw.competition || 0).toFixed(2),
            },
            {
              key: 'kei',
              header: 'KEI',
              width: '80px',
              align: 'right',
              render: (kw: Keyword) => (
                <span className="font-semibold text-primary">
                  {Number(kw.kei || 0).toFixed(1)}
                </span>
              ),
            },
            {
              key: 'difficulty',
              header: '난이도',
              width: '70px',
              align: 'right',
              render: (kw: Keyword) => Number(kw.difficulty || 0),
            },
            {
              key: 'opportunity',
              header: '기회',
              width: '70px',
              align: 'right',
              render: (kw: Keyword) => Number(kw.opportunity || 0),
            },
            {
              key: 'category',
              header: '카테고리',
              width: '100px',
              align: 'left',
              render: (kw: Keyword) => (
                <span className="text-muted-foreground">{kw.category || '-'}</span>
              ),
            },
            {
              key: 'trend',
              header: '트렌드',
              width: '100px',
              align: 'left',
              render: (kw: Keyword) => (
                kw.trend_status
                  ? `${TREND_ICONS[kw.trend_status] || ''} ${kw.trend_status}`
                  : '-'
              ),
            },
          ]}
        />
      </div>

      {/* KEI 분석 차트 (선택) */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📈 KEI 분석</h3>
        <p className="text-sm text-muted-foreground mb-4">
          KEI (Keyword Effectiveness Index) = 검색량² / 경쟁도
        </p>

        {/* KEI 분포 통계 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'KEI 500+', color: 'text-red-500', count: filteredKeywords.filter((k: Keyword) => (k.kei || 0) >= 500).length },
            { label: 'KEI 200-499', color: 'text-orange-500', count: filteredKeywords.filter((k: Keyword) => (k.kei || 0) >= 200 && (k.kei || 0) < 500).length },
            { label: 'KEI 100-199', color: 'text-yellow-500', count: filteredKeywords.filter((k: Keyword) => (k.kei || 0) >= 100 && (k.kei || 0) < 200).length },
            { label: 'KEI <100', color: 'text-muted-foreground', count: filteredKeywords.filter((k: Keyword) => (k.kei || 0) < 100).length },
          ].map((stat) => (
            <div key={stat.label} className="text-center p-4 bg-muted rounded-lg">
              <div className={`text-2xl font-bold ${stat.color}`}>{stat.count}</div>
              <div className="text-xs text-muted-foreground mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
