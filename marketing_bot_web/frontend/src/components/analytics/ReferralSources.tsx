/**
 * [Phase M-3] 유입 경로 분석 컴포넌트
 * "어떻게 오셨어요?" 응답 기반 유입 경로 통계
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Map,
  Plus,
  RefreshCw,
  Search,
  Instagram,
  FileText,
  Users,
  MapPin,
  Megaphone,
  MoreHorizontal,
  X,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState, EmptyState } from './shared'
import Button, { IconButton } from '@/components/ui/Button'
import type { ReferralSourcesData, ReferralSourceItem } from '@/types/analytics'

interface ReferralSourcesProps {
  compact?: boolean
  days?: number
}

export default function ReferralSources({ compact = false, days = 90 }: ReferralSourcesProps) {
  const [showAddModal, setShowAddModal] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<ReferralSourcesData>({
    queryKey: ['referral-sources', days],
    queryFn: () => analyticsApi.getReferralSources(days),
    staleTime: 300000, // 5분
  })

  if (isLoading) {
    return <LoadingState message="유입 경로 분석 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="유입 경로 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { by_source, total, insights, suggested_sources, message } = data

  // 유입 경로 아이콘 매핑
  const sourceIcons: Record<string, React.ReactNode> = {
    '네이버 검색': <Search className="w-4 h-4" />,
    '인스타그램': <Instagram className="w-4 h-4" />,
    '블로그': <FileText className="w-4 h-4" />,
    '지인 소개': <Users className="w-4 h-4" />,
    '지인 SNS': <Users className="w-4 h-4" />,
    '간판': <MapPin className="w-4 h-4" />,
    '근처 거주': <MapPin className="w-4 h-4" />,
    '온라인 광고': <Megaphone className="w-4 h-4" />,
    '전단지': <FileText className="w-4 h-4" />,
    '기타': <MoreHorizontal className="w-4 h-4" />,
  }

  // 빈 데이터
  if (total === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Map className="w-5 h-5 text-primary" aria-hidden="true" />
            유입 경로 분석
          </h2>
        </div>
        <EmptyState
          message={message || "유입 경로 데이터가 없습니다. 환자 방문 시 '어떻게 오셨어요?' 응답을 기록해주세요."}
        />
        <Button
          variant="primary"
          fullWidth
          onClick={() => setShowAddModal(true)}
          icon={<Plus className="w-4 h-4" />}
          className="mt-4"
        >
          유입 경로 기록하기
        </Button>

        {showAddModal && (
          <AddReferralModal
            suggestedSources={suggested_sources}
            onClose={() => setShowAddModal(false)}
            onSuccess={() => {
              setShowAddModal(false)
              queryClient.invalidateQueries({ queryKey: ['referral-sources'] })
            }}
          />
        )}
      </div>
    )
  }

  // 컴팩트 모드
  if (compact) {
    const topSources = by_source.slice(0, 3)

    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Map className="w-4 h-4 text-primary" aria-hidden="true" />
            유입 경로
          </h3>
          <span className="text-sm text-muted-foreground">총 {total}건</span>
        </div>

        <div className="space-y-2">
          {topSources.map((source: ReferralSourceItem) => (
            <div key={source.source} className="flex items-center gap-2">
              <span className="text-muted-foreground" aria-hidden="true">
                {sourceIcons[source.source] || sourceIcons['기타']}
              </span>
              <span className="flex-1 text-sm truncate">{source.source}</span>
              <span className="text-sm font-medium">{source.percentage}%</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Map className="w-5 h-5 text-primary" aria-hidden="true" />
              유입 경로 분석
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              최근 {days}일 / 총 {total}건 기록
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowAddModal(true)}
              icon={<Plus className="w-4 h-4" />}
            >
              기록 추가
            </Button>
            <IconButton
              icon={<RefreshCw className={`w-5 h-5 ${isRefetching ? 'animate-spin' : ''}`} />}
              onClick={() => refetch()}
              disabled={isRefetching}
              title="유입 경로 새로고침"
            />
          </div>
        </div>
      </div>

      {/* 유입 경로 차트 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">유입 경로별 비율</h3>
        <div className="space-y-3">
          {by_source.map((source: ReferralSourceItem) => (
            <div key={source.source}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground" aria-hidden="true">
                    {sourceIcons[source.source] || sourceIcons['기타']}
                  </span>
                  <span className="text-sm">{source.source}</span>
                </div>
                <span className="text-sm font-medium">{source.count}건 ({source.percentage}%)</span>
              </div>
              <div className="h-3 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary"
                  style={{ width: `${source.percentage}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 인사이트 */}
      {insights.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">인사이트</h3>
          <div className="space-y-2">
            {insights.map((insight: string, idx: number) => (
              <div key={idx} className="text-sm bg-muted/50 rounded p-3">
                {insight}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 유입 경로 추가 모달 */}
      {showAddModal && (
        <AddReferralModal
          suggestedSources={suggested_sources}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false)
            queryClient.invalidateQueries({ queryKey: ['referral-sources'] })
          }}
        />
      )}
    </div>
  )
}

// 유입 경로 추가 모달
function AddReferralModal({
  suggestedSources,
  onClose,
  onSuccess,
}: {
  suggestedSources: string[]
  onClose: () => void
  onSuccess: () => void
}) {
  const [selectedSource, setSelectedSource] = useState('')
  const [customSource, setCustomSource] = useState('')
  const [sourceDetail, setSourceDetail] = useState('')

  const mutation = useMutation({
    mutationFn: (data: { source: string; source_detail?: string }) =>
      analyticsApi.recordReferralSource(data),
    onSuccess: () => {
      onSuccess()
    },
  })

  const handleSubmit = () => {
    const source = selectedSource === '기타' ? customSource : selectedSource
    if (!source) return

    mutation.mutate({
      source,
      source_detail: sourceDetail || undefined,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg border border-border w-full max-w-md mx-4">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h3 className="font-semibold">유입 경로 기록</h3>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            title="닫기"
          />
        </div>

        <div className="p-4 space-y-4">
          {/* 유입 경로 선택 */}
          <div>
            <label className="text-sm font-medium mb-2 block">어떻게 오셨어요?</label>
            <div className="grid grid-cols-2 gap-2">
              {suggestedSources.map((source) => (
                <Button
                  key={source}
                  variant={selectedSource === source ? 'primary' : 'ghost'}
                  onClick={() => setSelectedSource(source)}
                  className={`p-3 h-auto justify-start text-left ${
                    selectedSource !== source ? 'bg-muted hover:bg-muted/80' : ''
                  }`}
                >
                  {source}
                </Button>
              ))}
            </div>
          </div>

          {/* 기타 선택 시 직접 입력 */}
          {selectedSource === '기타' && (
            <div>
              <label className="text-sm font-medium mb-2 block">직접 입력</label>
              <input
                type="text"
                value={customSource}
                onChange={(e) => setCustomSource(e.target.value)}
                placeholder="유입 경로를 입력하세요"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background"
              />
            </div>
          )}

          {/* 상세 정보 (선택) */}
          <div>
            <label className="text-sm font-medium mb-2 block">
              상세 정보 <span className="text-muted-foreground">(선택)</span>
            </label>
            <input
              type="text"
              value={sourceDetail}
              onChange={(e) => setSourceDetail(e.target.value)}
              placeholder="예: 검색어, 소개한 사람 이름 등"
              className="w-full px-3 py-2 rounded-lg border border-border bg-background"
            />
          </div>
        </div>

        <div className="p-4 border-t border-border flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!selectedSource || (selectedSource === '기타' && !customSource)}
            loading={mutation.isPending}
          >
            저장
          </Button>
        </div>
      </div>
    </div>
  )
}
