import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { pathfinderApi } from '@/services/api'
import { RefreshCw, TrendingUp, Zap, Target, AlertCircle } from 'lucide-react'
import { useState } from 'react'
import Button, { IconButton } from '@/components/ui/Button'
import GlossaryTerm from '@/components/ui/GlossaryTerm'

interface KeiKeyword {
  keyword: string
  search_volume: number
  difficulty: number
  opportunity: number
  grade: string
  category: string
  kei: number
  calculated_kei: number
  kei_grade: string
}

interface TopKeiKeywordsProps {
  limit?: number
  minVolume?: number
  compact?: boolean  // Dashboard용 간결 모드
  onNavigate?: () => void  // Pathfinder로 이동 콜백
}

export default function TopKeiKeywords({ limit = 10, minVolume = 10, compact = false, onNavigate }: TopKeiKeywordsProps) {
  const queryClient = useQueryClient()
  const [showAll, setShowAll] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['top-kei-keywords', limit, minVolume],
    queryFn: () => pathfinderApi.getTopKeiKeywords(showAll ? 50 : limit, minVolume),
    staleTime: 5 * 60 * 1000, // 5분
  })

  const recalculateMutation = useMutation({
    mutationFn: pathfinderApi.recalculateKei,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['top-kei-keywords'] })
      queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
    },
  })

  const getKeiGradeStyle = (grade: string) => {
    switch (grade) {
      case 'S':
        return 'bg-gradient-to-r from-yellow-400 to-amber-500 text-white'
      case 'A':
        return 'bg-gradient-to-r from-blue-400 to-blue-500 text-white'
      case 'B':
        return 'bg-gradient-to-r from-green-400 to-green-500 text-white'
      default:
        return 'bg-gray-400 text-white'
    }
  }

  const getKeiIcon = (grade: string) => {
    switch (grade) {
      case 'S':
        return <Zap className="w-3 h-3" />
      case 'A':
        return <TrendingUp className="w-3 h-3" />
      default:
        return <Target className="w-3 h-3" />
    }
  }

  const keywords: KeiKeyword[] = data?.keywords || []

  // 컴팩트 모드 (Dashboard용)
  if (compact) {
    if (isLoading) {
      return (
        <div className="bg-card rounded-lg border border-border p-4 animate-pulse">
          <div className="h-5 bg-muted rounded w-1/2 mb-3" />
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-8 bg-muted rounded" />
            ))}
          </div>
        </div>
      )
    }

    if (error || keywords.length === 0) {
      return null // 컴팩트 모드에서는 에러/빈 상태 시 숨김
    }

    const displayLimit = Math.min(5, limit)
    const topKeywords = keywords.slice(0, displayLimit)

    return (
      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-gradient-to-r from-primary/5 to-transparent flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-sm"><GlossaryTerm termKey="kei">KEI</GlossaryTerm> 상위 키워드</h3>
            <span className="px-1.5 py-0.5 bg-primary/10 text-primary text-[10px] font-medium rounded">
              TOP {displayLimit}
            </span>
          </div>
          {onNavigate && (
            <Button
              variant="ghost"
              size="xs"
              onClick={onNavigate}
            >
              더보기 →
            </Button>
          )}
        </div>
        <div className="divide-y divide-border">
          {topKeywords.map((kw, index) => (
            <div
              key={kw.keyword}
              className="px-4 py-2.5 hover:bg-accent/30 transition-colors flex items-center gap-2"
            >
              <span className="w-5 h-5 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold">
                {index + 1}
              </span>
              <span className="flex-1 text-sm truncate">{kw.keyword}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold flex items-center gap-0.5 ${getKeiGradeStyle(kw.kei_grade)}`}>
                {getKeiIcon(kw.kei_grade)}
                {kw.kei_grade}
              </span>
              <span className="text-xs text-primary font-medium w-12 text-right">
                {(kw.calculated_kei || kw.kei || 0).toFixed(1)}
              </span>
            </div>
          ))}
        </div>
        <div className="px-4 py-2 bg-muted/20 border-t border-border">
          <p className="text-[10px] text-muted-foreground text-center">
            KEI가 높을수록 공략 효율 ↑
          </p>
        </div>
      </div>
    )
  }

  // 기존 전체 모드
  if (isLoading) {
    return (
      <div className="bg-card rounded-xl border border-border p-4 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="h-10 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-card rounded-xl border border-border p-4">
        <div className="flex items-center gap-2 text-red-500">
          <AlertCircle className="w-5 h-5" />
          <span>KEI 데이터를 불러올 수 없습니다</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden">
      {/* 헤더 */}
      <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-primary/10 rounded-lg">
            <TrendingUp className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-sm"><GlossaryTerm termKey="kei">KEI</GlossaryTerm> 상위 키워드</h3>
            <p className="text-xs text-muted-foreground">
              검색량 대비 경쟁이 낮은 효율적인 키워드
            </p>
          </div>
        </div>
        <IconButton
          icon={<RefreshCw className={`w-4 h-4 ${recalculateMutation.isPending ? 'animate-spin' : ''}`} />}
          onClick={() => recalculateMutation.mutate()}
          disabled={recalculateMutation.isPending}
          size="sm"
          title="KEI 재계산"
        />
      </div>

      {/* 키워드 목록 */}
      {keywords.length === 0 ? (
        <div className="p-8 text-center text-muted-foreground">
          <Target className="w-10 h-10 mx-auto mb-2 opacity-50" />
          <p>KEI 데이터가 없습니다</p>
          <p className="text-xs mt-1">키워드 스캔을 먼저 실행해주세요</p>
        </div>
      ) : (
        <>
          <div className="divide-y divide-border">
            {keywords.slice(0, showAll ? 50 : 10).map((kw, index) => (
              <div
                key={kw.keyword}
                className="px-4 py-3 hover:bg-accent/50 transition-colors flex items-center gap-3"
              >
                {/* 순위 */}
                <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-xs font-bold">
                  {index + 1}
                </div>

                {/* 키워드 정보 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{kw.keyword}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold flex items-center gap-0.5 ${getKeiGradeStyle(kw.kei_grade)}`}>
                      {getKeiIcon(kw.kei_grade)}
                      {kw.kei_grade}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                    <span>검색량: {kw.search_volume?.toLocaleString() || 0}</span>
                    <span>난이도: {kw.difficulty || 0}</span>
                    <span className="text-primary font-medium">
                      KEI: {(kw.calculated_kei || kw.kei || 0).toFixed(1)}
                    </span>
                  </div>
                </div>

                {/* 카테고리 */}
                <span className="px-2 py-1 bg-muted rounded text-xs hidden sm:block">
                  {kw.category || '기타'}
                </span>
              </div>
            ))}
          </div>

          {/* 더보기 버튼 */}
          {keywords.length > 10 && (
            <div className="px-4 py-3 border-t border-border">
              <Button
                variant="ghost"
                size="sm"
                fullWidth
                onClick={() => setShowAll(!showAll)}
              >
                {showAll ? '접기' : `전체 ${keywords.length}개 보기`}
              </Button>
            </div>
          )}
        </>
      )}

      {/* 안내 */}
      <div className="px-4 py-2 bg-muted/30 border-t border-border">
        <p className="text-xs text-muted-foreground">
          <strong>KEI</strong> = (검색량 / 난이도) × 10 | 높을수록 공략 효율 ↑
        </p>
      </div>
    </div>
  )
}
