/**
 * A/B 테스트 관리 컴포넌트
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'
import {
  FlaskConical, Plus, Play, Pause, CheckCircle, Trophy,
  BarChart3, Users, TrendingUp, RefreshCw, X
} from 'lucide-react'
import type { ABExperiment, ABVariant } from '@/types/marketing'

const STATUS_CONFIG = {
  draft: { label: '초안', color: 'bg-gray-500' },
  running: { label: '실행 중', color: 'bg-green-500' },
  paused: { label: '일시중지', color: 'bg-yellow-500' },
  completed: { label: '완료', color: 'bg-blue-500' },
}

const EXPERIMENT_TYPES = [
  { value: 'comment_style', label: '댓글 스타일' },
  { value: 'timing', label: '게시 시간' },
  { value: 'template', label: '템플릿 비교' },
]

export function ABTestManager() {
  const [showCreateModal, setShowCreateModal] = useState(false)

  const queryClient = useQueryClient()
  const toast = useToast()

  const { data, isLoading, error, refetch, isRefetching } = useQuery<ABExperiment[]>({
    queryKey: ['ab-tests'],
    queryFn: marketingApi.getABTests,
    staleTime: 60 * 1000, // [Phase 7] 30초 → 60초
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      marketingApi.updateABTestStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ab-tests'] })
      toast.success('A/B 테스트 상태가 변경되었습니다.')
    },
    onError: () => {
      toast.error('상태 변경에 실패했습니다.')
    },
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-4">
          {[1, 2].map(i => (
            <div key={i} className="h-40 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">A/B 테스트 목록을 불러올 수 없습니다.</p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
        >
          다시 시도
        </Button>
      </div>
    )
  }

  const experiments = data || []

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-purple-500" />
          A/B 테스트
        </h2>
        <div className="flex items-center gap-4">
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="새로고침"
          />
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
            icon={<Plus className="w-4 h-4" />}
          >
            새 실험
          </Button>
        </div>
      </div>

      {/* 실험 목록 */}
      {experiments.length === 0 ? (
        <div className="bg-card border border-border rounded-lg p-12 text-center">
          <FlaskConical className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <h3 className="text-lg font-semibold mb-2">실험이 없습니다</h3>
          <p className="text-muted-foreground mb-4">
            새 A/B 테스트를 만들어 댓글 효과를 측정해보세요.
          </p>
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
          >
            첫 실험 만들기
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {experiments.map((exp) => (
            <ExperimentCard
              key={exp.id}
              experiment={exp}
              onStatusChange={(status) => statusMutation.mutate({ id: exp.id, status })}
              isUpdating={statusMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* 생성 모달 */}
      {showCreateModal && (
        <CreateExperimentModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false)
            refetch()
          }}
        />
      )}
    </div>
  )
}

interface ExperimentCardProps {
  experiment: ABExperiment
  onStatusChange: (status: string) => void
  isUpdating: boolean
}

function ExperimentCard({ experiment, onStatusChange, isUpdating }: ExperimentCardProps) {
  const statusConfig = STATUS_CONFIG[experiment.status] || STATUS_CONFIG.draft
  const hasWinner = experiment.winner_variant_id !== null

  // 통계적 유의성 계산 (간단한 근사)
  const calculateSignificance = (variants: ABVariant[]) => {
    if (variants.length < 2) return null
    const [control, ...treatments] = variants
    if (control.impressions < 30) return null

    const bestTreatment = treatments.reduce((best, v) =>
      v.conversion_rate > best.conversion_rate ? v : best
    , treatments[0])

    if (!bestTreatment || bestTreatment.impressions < 30) return null

    const improvement = ((bestTreatment.conversion_rate - control.conversion_rate) / (control.conversion_rate || 1)) * 100

    return {
      winner: bestTreatment,
      improvement: improvement.toFixed(1),
      significant: Math.abs(improvement) > 10 && bestTreatment.impressions >= 50
    }
  }

  const significance = calculateSignificance(experiment.variants)

  return (
    <div className="bg-card border border-border rounded-lg p-6">
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-1 rounded text-xs font-medium text-white ${statusConfig.color}`}>
              {statusConfig.label}
            </span>
            <h3 className="text-lg font-semibold">{experiment.name}</h3>
            {hasWinner && (
              <Trophy className="w-5 h-5 text-yellow-500" />
            )}
          </div>
          {experiment.description && (
            <p className="text-sm text-muted-foreground mt-1">{experiment.description}</p>
          )}
        </div>

        {/* 상태 변경 버튼 */}
        <div className="flex items-center gap-2">
          {experiment.status === 'draft' && (
            <Button
              variant="success"
              size="sm"
              onClick={() => onStatusChange('running')}
              loading={isUpdating}
              icon={<Play className="w-3 h-3" />}
            >
              시작
            </Button>
          )}
          {experiment.status === 'running' && (
            <Button
              size="sm"
              onClick={() => onStatusChange('paused')}
              loading={isUpdating}
              icon={<Pause className="w-3 h-3" />}
              className="bg-yellow-600 hover:bg-yellow-700"
            >
              일시중지
            </Button>
          )}
          {experiment.status === 'paused' && (
            <>
              <Button
                variant="success"
                size="sm"
                onClick={() => onStatusChange('running')}
                loading={isUpdating}
                icon={<Play className="w-3 h-3" />}
              >
                재개
              </Button>
              <Button
                size="sm"
                onClick={() => onStatusChange('completed')}
                loading={isUpdating}
                icon={<CheckCircle className="w-3 h-3" />}
                className="bg-blue-600 hover:bg-blue-700"
              >
                완료
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 진행률 */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="text-muted-foreground">샘플 수집</span>
          <span className="font-medium">
            {experiment.total_impressions} / {experiment.sample_size_target} ({experiment.progress_percent}%)
          </span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              experiment.progress_percent >= 100 ? 'bg-green-500' : 'bg-blue-500'
            }`}
            style={{ width: `${Math.min(experiment.progress_percent, 100)}%` }}
          />
        </div>
      </div>

      {/* 변형 통계 */}
      <div className="space-y-3">
        {experiment.variants.map((variant, idx) => (
          <VariantRow
            key={variant.id}
            variant={variant}
            isControl={idx === 0}
            isWinner={experiment.winner_variant_id === variant.id}
          />
        ))}
      </div>

      {/* 통계적 유의성 */}
      {significance && (
        <div className={`mt-4 p-3 rounded-lg ${
          significance.significant ? 'bg-green-500/10 border border-green-500/30' : 'bg-muted'
        }`}>
          {significance.significant ? (
            <div className="flex items-center gap-2">
              <Trophy className="w-4 h-4 text-yellow-500" />
              <span className="font-medium">
                "{significance.winner.name}"이(가) 대조군 대비 {significance.improvement}% 더 나은 성과
              </span>
              <span className="text-xs text-green-500">(통계적 유의미)</span>
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">
              아직 통계적으로 유의미한 결과가 나오지 않았습니다. 더 많은 샘플이 필요합니다.
            </span>
          )}
        </div>
      )}
    </div>
  )
}

interface VariantRowProps {
  variant: ABVariant
  isControl: boolean
  isWinner: boolean
}

function VariantRow({ variant, isControl, isWinner }: VariantRowProps) {
  return (
    <div className={`flex items-center gap-4 p-3 rounded-lg ${
      isWinner ? 'bg-yellow-500/10 border border-yellow-500/30' : 'bg-muted/50'
    }`}>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{variant.name}</span>
          {isControl && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-500 text-white rounded">대조군</span>
          )}
          {isWinner && (
            <Trophy className="w-4 h-4 text-yellow-500" />
          )}
        </div>
        {variant.description && (
          <p className="text-xs text-muted-foreground mt-0.5">{variant.description}</p>
        )}
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div className="text-center">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Users className="w-3 h-3" />
            <span>{variant.impressions}</span>
          </div>
          <div className="text-xs text-muted-foreground">노출</div>
        </div>
        <div className="text-center">
          <div className="flex items-center gap-1 text-blue-500">
            <BarChart3 className="w-3 h-3" />
            <span>{variant.engagement_rate.toFixed(1)}%</span>
          </div>
          <div className="text-xs text-muted-foreground">반응률</div>
        </div>
        <div className="text-center">
          <div className="flex items-center gap-1 text-green-500">
            <TrendingUp className="w-3 h-3" />
            <span>{variant.conversion_rate.toFixed(1)}%</span>
          </div>
          <div className="text-xs text-muted-foreground">전환율</div>
        </div>
      </div>
    </div>
  )
}

interface CreateExperimentModalProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateExperimentModal({ onClose, onSuccess }: CreateExperimentModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    experiment_type: 'comment_style',
    sample_size_target: 100,
    variants: [
      { name: '대조군 (현재 방식)', description: '', content_template: '' },
      { name: '변형 A', description: '', content_template: '' },
    ]
  })

  const toast = useToast()

  const createMutation = useMutation({
    mutationFn: () => marketingApi.createABTest(formData),
    onSuccess: () => {
      toast.success('A/B 테스트가 생성되었습니다.')
      onSuccess()
    },
    onError: () => {
      toast.error('생성에 실패했습니다.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) {
      toast.error('실험 이름을 입력해주세요.')
      return
    }
    if (formData.variants.length < 2) {
      toast.error('최소 2개의 변형이 필요합니다.')
      return
    }
    createMutation.mutate()
  }

  const addVariant = () => {
    setFormData(prev => ({
      ...prev,
      variants: [...prev.variants, {
        name: `변형 ${String.fromCharCode(64 + prev.variants.length)}`,
        description: '',
        content_template: ''
      }]
    }))
  }

  const removeVariant = (index: number) => {
    if (formData.variants.length <= 2) return
    setFormData(prev => ({
      ...prev,
      variants: prev.variants.filter((_, i) => i !== index)
    }))
  }

  const updateVariant = (index: number, field: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      variants: prev.variants.map((v, i) =>
        i === index ? { ...v, [field]: value } : v
      )
    }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold">새 A/B 테스트 만들기</h3>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            size="sm"
            title="닫기"
          />
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">실험 이름 *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              placeholder="예: 공감형 vs 정보형 댓글 비교"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">설명</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              rows={2}
              placeholder="이 실험의 목적과 가설을 설명해주세요"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">실험 유형</label>
              <select
                value={formData.experiment_type}
                onChange={(e) => setFormData({ ...formData, experiment_type: e.target.value })}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              >
                {EXPERIMENT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">목표 샘플 수</label>
              <input
                type="number"
                value={formData.sample_size_target}
                onChange={(e) => setFormData({ ...formData, sample_size_target: parseInt(e.target.value) || 100 })}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
                min="30"
              />
            </div>
          </div>

          {/* 변형 섹션 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium">변형 ({formData.variants.length}개)</label>
              <Button
                variant="ghost"
                size="xs"
                type="button"
                onClick={addVariant}
              >
                + 변형 추가
              </Button>
            </div>

            <div className="space-y-3">
              {formData.variants.map((variant, idx) => (
                <div key={idx} className="p-3 border border-border rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">
                      {idx === 0 ? '대조군' : `변형 ${String.fromCharCode(64 + idx)}`}
                    </span>
                    {idx > 1 && (
                      <Button
                        variant="ghost"
                        size="xs"
                        type="button"
                        onClick={() => removeVariant(idx)}
                        className="text-red-500"
                      >
                        삭제
                      </Button>
                    )}
                  </div>
                  <input
                    type="text"
                    value={variant.name}
                    onChange={(e) => updateVariant(idx, 'name', e.target.value)}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm mb-2"
                    placeholder="변형 이름"
                  />
                  <textarea
                    value={variant.content_template}
                    onChange={(e) => updateVariant(idx, 'content_template', e.target.value)}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm"
                    rows={2}
                    placeholder="댓글 템플릿 또는 스타일 설명"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button
              variant="outline"
              type="button"
              onClick={onClose}
            >
              취소
            </Button>
            <Button
              variant="primary"
              type="submit"
              loading={createMutation.isPending}
            >
              실험 생성
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
