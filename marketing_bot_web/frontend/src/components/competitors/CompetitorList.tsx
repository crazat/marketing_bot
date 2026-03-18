import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { competitorsApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import { ConfirmModal } from '@/components/ui/Modal'
import Button, { IconButton } from '@/components/ui/Button'
import { Plus, Check, X, Edit2, Trash2 } from 'lucide-react'

interface Competitor {
  id: number
  name: string
  category: string
  priority: string
  keywords?: string[]
  monitor_urls?: {
    naver_place?: string
    instagram?: string
    blog?: string
  }
}

interface CompetitorListProps {
  competitors: Competitor[]
}

export default function CompetitorList({ competitors }: CompetitorListProps) {
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [competitorToDelete, setCompetitorToDelete] = useState<Competitor | null>(null)
  const [newCompetitor, setNewCompetitor] = useState({
    name: '',
    place_id: '',
    category: '한의원',
    priority: 'Medium'
  })
  const [editData, setEditData] = useState({
    name: '',
    category: '',
    priority: ''
  })
  const queryClient = useQueryClient()
  const toast = useToast()

  // 추가 mutation
  const addMutation = useMutation({
    mutationFn: () => competitorsApi.addCompetitor(
      newCompetitor.name,
      newCompetitor.place_id || undefined,
      newCompetitor.category,
      newCompetitor.priority
    ),
    onSuccess: () => {
      toast.success('경쟁사가 추가되었습니다')
      queryClient.invalidateQueries({ queryKey: ['competitors-list'] })
      setIsAddOpen(false)
      setNewCompetitor({ name: '', place_id: '', category: '한의원', priority: 'Medium' })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`추가 실패: ${error.response?.data?.detail || error.message}`)
    }
  })

  // 수정 mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; category?: string; priority?: string } }) =>
      competitorsApi.updateCompetitor(id, data),
    onSuccess: () => {
      toast.success('경쟁사 정보가 수정되었습니다')
      queryClient.invalidateQueries({ queryKey: ['competitors-list'] })
      setEditingId(null)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`수정 실패: ${error.response?.data?.detail || error.message}`)
    }
  })

  // 삭제 mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => competitorsApi.deleteCompetitor(id),
    onSuccess: () => {
      toast.success('경쟁사가 삭제되었습니다')
      queryClient.invalidateQueries({ queryKey: ['competitors-list'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`삭제 실패: ${error.response?.data?.detail || error.message}`)
    }
  })

  const handleAdd = () => {
    if (!newCompetitor.name.trim()) return
    addMutation.mutate()
  }

  const handleEdit = (comp: Competitor) => {
    setEditingId(comp.id)
    setEditData({
      name: comp.name,
      category: comp.category,
      priority: comp.priority
    })
  }

  const handleSaveEdit = () => {
    if (!editingId || !editData.name.trim()) return
    updateMutation.mutate({
      id: editingId,
      data: editData
    })
  }

  const handleDelete = (comp: Competitor) => {
    setCompetitorToDelete(comp)
  }

  const confirmDelete = () => {
    if (competitorToDelete) {
      deleteMutation.mutate(competitorToDelete.id)
      setCompetitorToDelete(null)
    }
  }

  // 우선순위에 따른 색상
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'Critical': return 'bg-red-500/20 text-red-500'
      case 'High': return 'bg-orange-500/20 text-orange-500'
      case 'Medium': return 'bg-yellow-500/20 text-yellow-500'
      case 'Low': return 'bg-blue-500/20 text-blue-500'
      default: return 'bg-muted text-muted-foreground'
    }
  }

  // 우선순위에 따른 이모지
  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'Critical': return '🔴'
      case 'High': return '🟠'
      case 'Medium': return '🟡'
      case 'Low': return '🔵'
      default: return '⚪'
    }
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold">🏢 경쟁사 목록</h2>
          <p className="text-sm text-muted-foreground mt-1">
            총 {competitors?.length || 0}개 경쟁사 모니터링 중
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setIsAddOpen(true)}
          icon={<Plus className="w-4 h-4" />}
        >
          경쟁사 추가
        </Button>
      </div>

      {/* 경쟁사 추가 폼 */}
      {isAddOpen && (
        <div className="mb-6 p-4 rounded-lg border border-primary/50 bg-primary/5">
          <h3 className="font-semibold mb-4">새 경쟁사 추가</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label htmlFor="competitor-name" className="block text-sm text-muted-foreground mb-1">상호명 *</label>
              <input
                id="competitor-name"
                type="text"
                value={newCompetitor.name}
                onChange={(e) => setNewCompetitor({ ...newCompetitor, name: e.target.value })}
                placeholder="예: 청주한의원"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label htmlFor="competitor-place-url" className="block text-sm text-muted-foreground mb-1">네이버 플레이스 URL (선택)</label>
              <input
                id="competitor-place-url"
                type="text"
                value={newCompetitor.place_id}
                onChange={(e) => setNewCompetitor({ ...newCompetitor, place_id: e.target.value })}
                placeholder="https://m.place.naver.com/hospital/..."
                className="w-full px-3 py-2 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label htmlFor="competitor-category" className="block text-sm text-muted-foreground mb-1">카테고리</label>
              <select
                id="competitor-category"
                value={newCompetitor.category}
                onChange={(e) => setNewCompetitor({ ...newCompetitor, category: e.target.value })}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              >
                <option value="Diet">Diet (다이어트)</option>
                <option value="Skin">Skin (피부)</option>
                <option value="Pain/Body">Pain/Body (통증/체형)</option>
                <option value="Pain/Traffic">Pain/Traffic (교통사고)</option>
                <option value="Pain/Chuna">Pain/Chuna (추나)</option>
                <option value="Face">Face (안면)</option>
                <option value="Benchmark">Benchmark (벤치마크)</option>
              </select>
            </div>
            <div>
              <label htmlFor="competitor-priority" className="block text-sm text-muted-foreground mb-1">우선순위</label>
              <select
                id="competitor-priority"
                value={newCompetitor.priority}
                onChange={(e) => setNewCompetitor({ ...newCompetitor, priority: e.target.value })}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              >
                <option value="Critical">Critical (최우선)</option>
                <option value="High">High (높음)</option>
                <option value="Medium">Medium (중간)</option>
                <option value="Low">Low (낮음/벤치마크)</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="success"
              onClick={handleAdd}
              disabled={!newCompetitor.name.trim()}
              loading={addMutation.isPending}
              icon={<Check className="w-4 h-4" />}
            >
              추가
            </Button>
            <Button
              variant="secondary"
              onClick={() => setIsAddOpen(false)}
            >
              취소
            </Button>
          </div>
        </div>
      )}

      {/* 통계 카드 */}
      {competitors && competitors.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30">
            <div className="text-2xl font-bold text-red-500">
              {competitors.filter(c => c.priority === 'Critical').length}
            </div>
            <div className="text-xs text-muted-foreground">Critical</div>
          </div>
          <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/30">
            <div className="text-2xl font-bold text-orange-500">
              {competitors.filter(c => c.priority === 'High').length}
            </div>
            <div className="text-xs text-muted-foreground">High</div>
          </div>
          <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
            <div className="text-2xl font-bold text-yellow-500">
              {competitors.filter(c => c.priority === 'Medium').length}
            </div>
            <div className="text-xs text-muted-foreground">Medium</div>
          </div>
          <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
            <div className="text-2xl font-bold text-blue-500">
              {competitors.filter(c => c.priority === 'Low').length}
            </div>
            <div className="text-xs text-muted-foreground">Low / Benchmark</div>
          </div>
        </div>
      )}

      {!competitors || competitors.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-4xl mb-4">🏢</p>
          <p>등록된 경쟁사가 없습니다.</p>
          <p className="text-sm mt-2">경쟁사를 추가하여 모니터링을 시작하세요.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-sm font-semibold">상호명</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">카테고리</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">우선순위</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">모니터링 키워드</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">링크</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">액션</th>
              </tr>
            </thead>
            <tbody>
              {competitors.map((comp: Competitor) => (
                <tr
                  key={comp.id}
                  className="border-b border-border hover:bg-accent/50 transition-colors"
                >
                  {editingId === comp.id ? (
                    // 수정 모드
                    <>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={editData.name}
                          onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                          className="w-full px-2 py-1 rounded border border-border bg-background text-sm"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={editData.category}
                          onChange={(e) => setEditData({ ...editData, category: e.target.value })}
                          className="px-2 py-1 rounded border border-border bg-background text-sm"
                        >
                          <option value="Diet">Diet</option>
                          <option value="Skin">Skin</option>
                          <option value="Pain/Body">Pain/Body</option>
                          <option value="Pain/Traffic">Pain/Traffic</option>
                          <option value="Pain/Chuna">Pain/Chuna</option>
                          <option value="Face">Face</option>
                          <option value="Benchmark">Benchmark</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={editData.priority}
                          onChange={(e) => setEditData({ ...editData, priority: e.target.value })}
                          className="px-2 py-1 rounded border border-border bg-background text-sm"
                        >
                          <option value="Critical">Critical</option>
                          <option value="High">High</option>
                          <option value="Medium">Medium</option>
                          <option value="Low">Low</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">-</td>
                      <td className="px-4 py-3">-</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <IconButton
                            icon={<Check className="w-4 h-4" />}
                            onClick={handleSaveEdit}
                            disabled={updateMutation.isPending}
                            size="sm"
                            className="text-green-500 hover:bg-green-500/10"
                            title="저장"
                          />
                          <IconButton
                            icon={<X className="w-4 h-4" />}
                            onClick={() => setEditingId(null)}
                            size="sm"
                            title="취소"
                          />
                        </div>
                      </td>
                    </>
                  ) : (
                    // 보기 모드
                    <>
                      <td className="px-4 py-3 font-medium">{comp.name}</td>
                      <td className="px-4 py-3">
                        <span className="text-xs px-2 py-1 rounded-full bg-muted">
                          {comp.category}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-1 rounded-full ${getPriorityColor(comp.priority)}`}>
                          {getPriorityIcon(comp.priority)} {comp.priority}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {comp.keywords?.slice(0, 3).map((kw: string, i: number) => (
                            <span key={i} className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                              {kw}
                            </span>
                          ))}
                          {comp.keywords && comp.keywords.length > 3 && (
                            <span className="text-xs text-muted-foreground">
                              +{comp.keywords.length - 3}
                            </span>
                          )}
                          {(!comp.keywords || comp.keywords.length === 0) && (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {comp.monitor_urls?.naver_place && (
                            <a
                              href={comp.monitor_urls.naver_place}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-500 hover:underline"
                            >
                              플레이스
                            </a>
                          )}
                          {comp.monitor_urls?.instagram && (
                            <a
                              href={comp.monitor_urls.instagram}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-pink-500 hover:underline"
                            >
                              IG
                            </a>
                          )}
                          {comp.monitor_urls?.blog && (
                            <a
                              href={comp.monitor_urls.blog}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-green-500 hover:underline"
                            >
                              블로그
                            </a>
                          )}
                          {!comp.monitor_urls?.naver_place && !comp.monitor_urls?.instagram && !comp.monitor_urls?.blog && (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <IconButton
                            icon={<Edit2 className="w-4 h-4" />}
                            onClick={() => handleEdit(comp)}
                            size="sm"
                            className="text-blue-500 hover:bg-blue-500/10"
                            title="수정"
                            aria-label={`${comp.name} 수정`}
                          />
                          <IconButton
                            icon={<Trash2 className="w-4 h-4" />}
                            onClick={() => handleDelete(comp)}
                            disabled={deleteMutation.isPending}
                            size="sm"
                            className="text-red-500 hover:bg-red-500/10"
                            title="삭제"
                            aria-label={`${comp.name} 삭제`}
                          />
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 안내 메시지 */}
      <div className="mt-4 p-3 bg-muted/50 rounded-lg">
        <p className="text-xs text-muted-foreground">
          <strong>우선순위 설명:</strong> Critical/High/Medium 경쟁사는 순위 스캔 및 리뷰 수집 대상입니다.
          Low는 벤치마크용으로 스캔에서 제외됩니다.
        </p>
      </div>

      {/* 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={competitorToDelete !== null}
        onClose={() => setCompetitorToDelete(null)}
        onConfirm={confirmDelete}
        title="경쟁사 삭제"
        message={`"${competitorToDelete?.name}"을(를) 삭제하시겠습니까? 삭제하면 관련 리뷰 데이터는 유지되지만, 스캔 대상에서 제외됩니다.`}
        confirmText="삭제"
        cancelText="취소"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  )
}
