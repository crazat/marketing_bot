/**
 * [Phase 6.2] 경쟁사 순위 비교 컴포넌트
 * 우리 업체의 순위와 경쟁사 순위를 비교하여 표시
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { battleApi } from '@/services/api'
import { TrendingDown, Minus, Plus, Trophy, Users, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'

interface CompetitorComparison {
  keyword: string
  our_rank: number | null
  competitors: Array<{
    name: string
    rank: number
    scanned_at: string
  }>
  best_competitor: string | null
  our_position: string // 'leading', 'competitive', 'behind', 'not_ranked'
}

interface AddRankingForm {
  competitor_name: string
  keyword: string
  rank: number
  note: string
}

export default function CompetitorRankingCompare() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [isExpanded, setIsExpanded] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState<AddRankingForm>({
    competitor_name: '',
    keyword: '',
    rank: 1,
    note: '',
  })

  // 순위 비교 데이터 조회
  const { data, isLoading, error } = useQuery({
    queryKey: ['competitor-rankings-compare'],
    queryFn: () => battleApi.compareRankingsWithCompetitors(),
    staleTime: 5 * 60 * 1000, // 5분
  })

  // 경쟁사 순위 추가
  const addRankingMutation = useMutation({
    mutationFn: battleApi.addCompetitorRanking,
    onSuccess: () => {
      toast.success('경쟁사 순위가 등록되었습니다')
      queryClient.invalidateQueries({ queryKey: ['competitor-rankings-compare'] })
      setShowAddForm(false)
      setFormData({ competitor_name: '', keyword: '', rank: 1, note: '' })
    },
    onError: () => toast.error('순위 등록 실패'),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    addRankingMutation.mutate(formData)
  }

  const getPositionStyle = (position: string) => {
    switch (position) {
      case 'leading':
        return { bg: 'bg-green-500/10', text: 'text-green-500', icon: <Trophy className="w-4 h-4" /> }
      case 'competitive':
        return { bg: 'bg-yellow-500/10', text: 'text-yellow-500', icon: <Minus className="w-4 h-4" /> }
      case 'behind':
        return { bg: 'bg-red-500/10', text: 'text-red-500', icon: <TrendingDown className="w-4 h-4" /> }
      default:
        return { bg: 'bg-gray-500/10', text: 'text-gray-500', icon: <AlertCircle className="w-4 h-4" /> }
    }
  }

  const getPositionLabel = (position: string) => {
    switch (position) {
      case 'leading': return '선두'
      case 'competitive': return '경쟁'
      case 'behind': return '추격 필요'
      default: return '미순위'
    }
  }

  const comparisons: CompetitorComparison[] = data?.comparisons || []
  const summary = data?.summary || { leading: 0, competitive: 0, behind: 0, not_ranked: 0 }

  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden">
      {/* 헤더 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-primary/10 rounded-lg">
            <Users className="w-4 h-4 text-primary" />
          </div>
          <div className="text-left">
            <h3 className="font-semibold text-sm">경쟁사 순위 비교</h3>
            <p className="text-xs text-muted-foreground">
              키워드별 우리 순위 vs 경쟁사 순위
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* 요약 배지 */}
          <div className="hidden sm:flex items-center gap-2 text-xs">
            <span className="px-2 py-0.5 bg-green-500/20 text-green-500 rounded-full">
              선두 {summary.leading}
            </span>
            <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-500 rounded-full">
              경쟁 {summary.competitive}
            </span>
            <span className="px-2 py-0.5 bg-red-500/20 text-red-500 rounded-full">
              추격 {summary.behind}
            </span>
          </div>
          {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </div>
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* 로딩 상태 */}
          {isLoading && (
            <div className="text-center py-8 text-muted-foreground">
              <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
              <p>데이터 로딩 중...</p>
            </div>
          )}

          {/* 에러 상태 */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 text-red-500 rounded-lg">
              <AlertCircle className="w-5 h-5" />
              <span>데이터를 불러올 수 없습니다</span>
            </div>
          )}

          {/* 경쟁사 순위 추가 버튼 */}
          {!isLoading && (
            <div className="flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={() => setShowAddForm(!showAddForm)}
                icon={<Plus className="w-4 h-4" />}
              >
                경쟁사 순위 추가
              </Button>
            </div>
          )}

          {/* 순위 추가 폼 */}
          {showAddForm && (
            <form onSubmit={handleSubmit} className="bg-muted/30 rounded-lg p-4 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium mb-1">경쟁사명</label>
                  <input
                    type="text"
                    value={formData.competitor_name}
                    onChange={(e) => setFormData({ ...formData, competitor_name: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="예: OO한의원"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">키워드</label>
                  <input
                    type="text"
                    value={formData.keyword}
                    onChange={(e) => setFormData({ ...formData, keyword: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="예: 청주 한의원"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">순위</label>
                  <input
                    type="number"
                    value={formData.rank}
                    onChange={(e) => setFormData({ ...formData, rank: parseInt(e.target.value) || 1 })}
                    min={1}
                    required
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">메모 (선택)</label>
                  <input
                    type="text"
                    value={formData.note}
                    onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="특이사항"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowAddForm(false)}
                >
                  취소
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  type="submit"
                  loading={addRankingMutation.isPending}
                >
                  저장
                </Button>
              </div>
            </form>
          )}

          {/* 비교 테이블 */}
          {!isLoading && comparisons.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left font-medium">키워드</th>
                    <th className="px-3 py-2 text-center font-medium">우리 순위</th>
                    <th className="px-3 py-2 text-left font-medium">경쟁사 순위</th>
                    <th className="px-3 py-2 text-center font-medium">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.map((item) => {
                    const posStyle = getPositionStyle(item.our_position)
                    return (
                      <tr key={item.keyword} className="border-b border-border hover:bg-muted/30">
                        <td className="px-3 py-3 font-medium">{item.keyword}</td>
                        <td className="px-3 py-3 text-center">
                          {item.our_rank ? (
                            <span className={`font-bold ${item.our_rank <= 3 ? 'text-green-500' : item.our_rank <= 10 ? 'text-yellow-500' : 'text-muted-foreground'}`}>
                              {item.our_rank}위
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex flex-wrap gap-1">
                            {item.competitors.length > 0 ? (
                              item.competitors.slice(0, 3).map((comp) => (
                                <span
                                  key={comp.name}
                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                                    comp.rank < (item.our_rank || 999)
                                      ? 'bg-red-500/10 text-red-500'
                                      : comp.rank > (item.our_rank || 0)
                                      ? 'bg-green-500/10 text-green-500'
                                      : 'bg-yellow-500/10 text-yellow-500'
                                  }`}
                                >
                                  {comp.name}: {comp.rank}위
                                </span>
                              ))
                            ) : (
                              <span className="text-muted-foreground text-xs">경쟁사 데이터 없음</span>
                            )}
                            {item.competitors.length > 3 && (
                              <span className="text-xs text-muted-foreground">+{item.competitors.length - 3}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${posStyle.bg} ${posStyle.text}`}>
                            {posStyle.icon}
                            {getPositionLabel(item.our_position)}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* 빈 상태 */}
          {!isLoading && comparisons.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-10 h-10 mx-auto mb-2 opacity-50" />
              <p>경쟁사 순위 데이터가 없습니다</p>
              <p className="text-xs mt-1">'경쟁사 순위 추가' 버튼으로 데이터를 등록하세요</p>
            </div>
          )}

          {/* 안내 */}
          <div className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-3">
            <strong>상태 설명:</strong>
            <div className="flex flex-wrap gap-3 mt-1">
              <span className="flex items-center gap-1">
                <Trophy className="w-3 h-3 text-green-500" /> 선두: 모든 경쟁사보다 높은 순위
              </span>
              <span className="flex items-center gap-1">
                <Minus className="w-3 h-3 text-yellow-500" /> 경쟁: 경쟁사와 비슷한 순위
              </span>
              <span className="flex items-center gap-1">
                <TrendingDown className="w-3 h-3 text-red-500" /> 추격: 경쟁사보다 낮은 순위
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
