/**
 * 캠페인 관리 컴포넌트
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'
import {
  Megaphone, Plus, Play, Pause, CheckCircle, Clock, Target,
  TrendingUp, DollarSign, RefreshCw, X
} from 'lucide-react'
import type { Campaign } from '@/types/marketing'

const STATUS_CONFIG = {
  draft: { label: '초안', color: 'bg-gray-500', icon: Clock },
  active: { label: '활성', color: 'bg-green-500', icon: Play },
  paused: { label: '일시중지', color: 'bg-yellow-500', icon: Pause },
  completed: { label: '완료', color: 'bg-blue-500', icon: CheckCircle },
}

const CATEGORIES = [
  '다이어트', '비대칭/교정', '피부', '교통사고',
  '통증/디스크', '두통/어지럼', '소화기', '호흡기', '기타'
]

const PLATFORMS = [
  { value: 'cafe', label: '카페' },
  { value: 'blog', label: '블로그' },
  { value: 'kin', label: '지식인' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'instagram', label: '인스타' },
]

export function CampaignManager() {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')

  const queryClient = useQueryClient()
  const toast = useToast()

  const { data, isLoading, error, refetch, isRefetching } = useQuery<Campaign[]>({
    queryKey: ['campaigns', statusFilter],
    queryFn: () => marketingApi.getCampaigns(statusFilter || undefined),
    staleTime: 60 * 1000, // [Phase 7] 30초 → 60초
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      marketingApi.updateCampaignStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      toast.success('캠페인 상태가 변경되었습니다.')
    },
    onError: () => {
      toast.error('상태 변경에 실패했습니다.')
    },
  })

  const handleStatusChange = (campaign: Campaign, newStatus: string) => {
    statusMutation.mutate({ id: campaign.id, status: newStatus })
  }

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-32 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">캠페인 목록을 불러올 수 없습니다.</p>
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

  const campaigns = data || []

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Megaphone className="w-6 h-6 text-purple-500" />
          캠페인 관리
        </h2>
        <div className="flex items-center gap-4">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-muted border border-border rounded-lg text-sm"
          >
            <option value="">전체 상태</option>
            <option value="draft">초안</option>
            <option value="active">활성</option>
            <option value="paused">일시중지</option>
            <option value="completed">완료</option>
          </select>
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
            새 캠페인
          </Button>
        </div>
      </div>

      {/* 캠페인 목록 */}
      {campaigns.length === 0 ? (
        <div className="bg-card border border-border rounded-lg p-12 text-center">
          <Megaphone className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <h3 className="text-lg font-semibold mb-2">캠페인이 없습니다</h3>
          <p className="text-muted-foreground mb-4">
            새 캠페인을 만들어 마케팅 목표를 관리하세요.
          </p>
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
          >
            첫 캠페인 만들기
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {campaigns.map((campaign) => (
            <CampaignCard
              key={campaign.id}
              campaign={campaign}
              onStatusChange={handleStatusChange}
              isUpdating={statusMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* 생성 모달 */}
      {showCreateModal && (
        <CreateCampaignModal
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

interface CampaignCardProps {
  campaign: Campaign
  onStatusChange: (campaign: Campaign, status: string) => void
  isUpdating: boolean
}

function CampaignCard({ campaign, onStatusChange, isUpdating }: CampaignCardProps) {
  const statusConfig = STATUS_CONFIG[campaign.status] || STATUS_CONFIG.draft
  const StatusIcon = statusConfig.icon

  return (
    <div className="bg-card border border-border rounded-lg p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-1 rounded text-xs font-medium text-white ${statusConfig.color}`}>
              <StatusIcon className="w-3 h-3 inline mr-1" />
              {statusConfig.label}
            </span>
            <h3 className="text-lg font-semibold">{campaign.name}</h3>
          </div>
          {campaign.description && (
            <p className="text-sm text-muted-foreground mt-1">{campaign.description}</p>
          )}
        </div>

        {/* 상태 변경 버튼 */}
        <div className="flex items-center gap-2">
          {campaign.status === 'draft' && (
            <Button
              variant="success"
              size="sm"
              onClick={() => onStatusChange(campaign, 'active')}
              loading={isUpdating}
              icon={<Play className="w-3 h-3" />}
            >
              시작
            </Button>
          )}
          {campaign.status === 'active' && (
            <Button
              size="sm"
              onClick={() => onStatusChange(campaign, 'paused')}
              loading={isUpdating}
              icon={<Pause className="w-3 h-3" />}
              className="bg-yellow-600 hover:bg-yellow-700"
            >
              일시중지
            </Button>
          )}
          {campaign.status === 'paused' && (
            <>
              <Button
                variant="success"
                size="sm"
                onClick={() => onStatusChange(campaign, 'active')}
                loading={isUpdating}
                icon={<Play className="w-3 h-3" />}
              >
                재개
              </Button>
              <Button
                size="sm"
                onClick={() => onStatusChange(campaign, 'completed')}
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
          <span className="text-muted-foreground">진행률</span>
          <span className="font-medium">
            {campaign.kpi_summary.processed} / {campaign.total_target} ({campaign.progress_percent}%)
          </span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              campaign.progress_percent >= 100 ? 'bg-green-500' :
              campaign.progress_percent >= 70 ? 'bg-blue-500' :
              campaign.progress_percent >= 30 ? 'bg-yellow-500' :
              'bg-gray-400'
            }`}
            style={{ width: `${Math.min(campaign.progress_percent, 100)}%` }}
          />
        </div>
      </div>

      {/* KPI 요약 */}
      <div className="grid grid-cols-4 gap-4">
        <div className="text-center p-2 bg-muted/50 rounded-lg">
          <Target className="w-4 h-4 mx-auto mb-1 text-blue-500" />
          <div className="font-bold">{campaign.kpi_summary.processed}</div>
          <div className="text-xs text-muted-foreground">처리됨</div>
        </div>
        <div className="text-center p-2 bg-muted/50 rounded-lg">
          <TrendingUp className="w-4 h-4 mx-auto mb-1 text-purple-500" />
          <div className="font-bold">{campaign.kpi_summary.leads}</div>
          <div className="text-xs text-muted-foreground">리드</div>
        </div>
        <div className="text-center p-2 bg-muted/50 rounded-lg">
          <CheckCircle className="w-4 h-4 mx-auto mb-1 text-green-500" />
          <div className="font-bold">{campaign.kpi_summary.conversions}</div>
          <div className="text-xs text-muted-foreground">전환</div>
        </div>
        <div className="text-center p-2 bg-muted/50 rounded-lg">
          <DollarSign className="w-4 h-4 mx-auto mb-1 text-yellow-500" />
          <div className="font-bold">{(campaign.kpi_summary.revenue / 10000).toFixed(0)}만</div>
          <div className="text-xs text-muted-foreground">수익</div>
        </div>
      </div>

      {/* 타겟 정보 */}
      <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
        {campaign.target_categories.length > 0 && (
          <span>카테고리: {campaign.target_categories.slice(0, 3).join(', ')}</span>
        )}
        {campaign.target_platforms.length > 0 && (
          <span>플랫폼: {campaign.target_platforms.join(', ')}</span>
        )}
        {campaign.start_date && (
          <span>시작: {new Date(campaign.start_date).toLocaleDateString('ko-KR')}</span>
        )}
      </div>
    </div>
  )
}

interface CreateCampaignModalProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateCampaignModal({ onClose, onSuccess }: CreateCampaignModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    target_categories: [] as string[],
    target_platforms: [] as string[],
    daily_target: 10,
    total_target: 100,
    budget: 0,
  })

  const toast = useToast()

  const createMutation = useMutation({
    mutationFn: () => marketingApi.createCampaign(formData),
    onSuccess: () => {
      toast.success('캠페인이 생성되었습니다.')
      onSuccess()
    },
    onError: () => {
      toast.error('캠페인 생성에 실패했습니다.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) {
      toast.error('캠페인 이름을 입력해주세요.')
      return
    }
    createMutation.mutate()
  }

  const toggleCategory = (cat: string) => {
    setFormData(prev => ({
      ...prev,
      target_categories: prev.target_categories.includes(cat)
        ? prev.target_categories.filter(c => c !== cat)
        : [...prev.target_categories, cat]
    }))
  }

  const togglePlatform = (platform: string) => {
    setFormData(prev => ({
      ...prev,
      target_platforms: prev.target_platforms.includes(platform)
        ? prev.target_platforms.filter(p => p !== platform)
        : [...prev.target_platforms, platform]
    }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold">새 캠페인 만들기</h3>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            size="sm"
            title="닫기"
          />
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">캠페인 이름 *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              placeholder="예: 봄맞이 다이어트 캠페인"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">설명</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              rows={2}
              placeholder="캠페인 목표와 전략을 설명해주세요"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">타겟 카테고리</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => toggleCategory(cat)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors ${
                    formData.target_categories.includes(cat)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted hover:bg-muted/80'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">타겟 플랫폼</label>
            <div className="flex flex-wrap gap-2">
              {PLATFORMS.map(p => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => togglePlatform(p.value)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors ${
                    formData.target_platforms.includes(p.value)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted hover:bg-muted/80'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">일일 목표</label>
              <input
                type="number"
                value={formData.daily_target}
                onChange={(e) => setFormData({ ...formData, daily_target: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
                min="1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">총 목표</label>
              <input
                type="number"
                value={formData.total_target}
                onChange={(e) => setFormData({ ...formData, total_target: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
                min="1"
              />
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
              캠페인 생성
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
