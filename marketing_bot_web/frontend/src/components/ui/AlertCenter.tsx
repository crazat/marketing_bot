import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi } from '@/services/api'
import { TrendingUp, Zap, CheckCircle, RefreshCw, ArrowRight } from 'lucide-react'
import Button from '@/components/ui/Button'

// 데이터 타입 정의
interface RankAlertsData {
  critical_drops: Array<{
    keyword: string
    current_rank: number
    previous_rank: number
    rank_change: number
    severity: string
  }>
  warnings: Array<{
    keyword: string
    current_rank: number
    previous_rank: number
    rank_change: number
    severity: string
  }>
  recommendations: Array<{
    priority: string
    message: string
    action: string
    keywords?: string[]
  }>
  summary: {
    total_critical: number
    total_warnings: number
  }
}

interface OverdueLeadsData {
  overdue_followups: Array<{
    id: number
    title: string
    platform: string
    follow_up_date: string
    status: string
    days_overdue: number
  }>
  stale_leads: Array<{
    id: number
    title: string
    platform: string
    created_at: string
    status: string
  }>
  no_response_leads: Array<{
    id: number
    title: string
    platform: string
    last_contact: string
    status: string
  }>
  summary: {
    total_overdue: number
    total_stale: number
    total_no_response: number
    total_action_needed: number
  }
}

interface KeiAlertsData {
  new_high_kei: Array<{
    keyword: string
    grade: string
    search_volume: number
    difficulty: number
    kei: number
    category: string
  }>
  s_grade_kei: Array<{
    keyword: string
    kei: number
  }>
  opportunities: Array<{
    keyword: string
    grade: string
    kei: number
    search_volume: number
    difficulty: number
  }>
  alerts: Array<{
    type: string
    severity: string
    message: string
    count: number
  }>
  summary: {
    s_kei_count: number
    a_kei_count: number
    total_alerts: number
  }
}

interface AutoApprovalAlertsData {
  auto_approved: Array<{
    id: number
    platform: string
    title: string
    priority_score: number
    discovered_at: string
  }>
  pending_review: Array<{
    id: number
    platform: string
    title: string
    priority_score: number
  }>
  active_rules: Array<{
    id: number
    name: string
    condition_type: string
    is_active: boolean
  }>
  alerts: Array<{
    type: string
    severity: string
    message: string
    count: number
  }>
  summary: {
    auto_approved_count: number
    pending_review_count: number
    active_rules_count: number
    total_alerts: number
  }
}

type AlertTab = 'rank' | 'lead' | 'kei' | 'approval'

const platformIcons: Record<string, string> = {
  youtube: '📺',
  tiktok: '🎵',
  instagram: '📸',
  naver: '🟢',
  carrot: '🥕',
  cafe: '☕',
}

export default function AlertCenter() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<AlertTab>('rank')

  // 순위 알림 데이터
  const { data: rankData, isError: rankError, refetch: refetchRank } = useQuery<RankAlertsData>({
    queryKey: ['rank-alerts'],
    queryFn: hudApi.getRankAlerts,
    refetchInterval: 300000,
    retry: 1,
  })

  // 리드 알림 데이터
  const { data: leadData, isError: leadError, refetch: refetchLead } = useQuery<OverdueLeadsData>({
    queryKey: ['overdue-leads'],
    queryFn: hudApi.getOverdueLeads,
    refetchInterval: 300000,
    retry: 1,
  })

  // [Phase 6.2] KEI 알림 데이터
  const { data: keiData, isError: keiError, refetch: refetchKei } = useQuery<KeiAlertsData>({
    queryKey: ['kei-alerts'],
    queryFn: () => hudApi.getKeiAlerts(7),
    refetchInterval: 300000,
    retry: 1,
  })

  // [Phase 6.2] 자동 승인 알림 데이터
  const { data: approvalData, isError: approvalError, refetch: refetchApproval } = useQuery<AutoApprovalAlertsData>({
    queryKey: ['auto-approval-alerts'],
    queryFn: () => hudApi.getAutoApprovalAlerts(7),
    refetchInterval: 300000,
    retry: 1,
  })

  // 알림 카운트 계산
  const rankAlertCount = (rankData?.summary.total_critical || 0) + (rankData?.summary.total_warnings || 0)
  const leadAlertCount = leadData?.summary.total_action_needed || 0
  const keiAlertCount = keiData?.summary.total_alerts || 0
  const approvalAlertCount = approvalData?.summary.total_alerts || 0
  const totalAlerts = rankAlertCount + leadAlertCount + keiAlertCount + approvalAlertCount

  // 알림이 없으면 표시 안함
  if (totalAlerts === 0) {
    return null
  }

  // 가장 심각한 알림 유형 확인
  const hasCritical = (rankData?.summary.total_critical || 0) > 0
  const hasRankWarnings = (rankData?.summary.total_warnings || 0) > 0

  // 배경색 결정
  const getBgColor = () => {
    if (hasCritical) return 'bg-red-500/10 border-red-500/30'
    if (hasRankWarnings) return 'bg-yellow-500/10 border-yellow-500/30'
    if (leadAlertCount > 0) return 'bg-amber-500/10 border-amber-500/30'
    return 'bg-blue-500/10 border-blue-500/30'
  }

  return (
    <div className={`rounded-lg p-4 mb-6 border ${getBgColor()}`}>
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold flex items-center gap-2">
          <span className="text-xl">{hasCritical ? '🚨' : '🔔'}</span>
          <span>알림 센터</span>
          <span className={`px-2 py-0.5 text-xs rounded-full ${
            hasCritical ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'
          }`}>
            {totalAlerts}
          </span>
        </h3>
      </div>

      {/* 탭 */}
      <div className="flex flex-wrap gap-2 mb-3">
        <button
          onClick={() => setActiveTab('rank')}
          className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
            activeTab === 'rank'
              ? 'bg-card border border-border shadow-sm'
              : 'hover:bg-muted/50'
          }`}
        >
          <span>📊</span>
          <span>순위 변동</span>
          {rankAlertCount > 0 && (
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
              hasCritical ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'
            }`}>
              {rankAlertCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('lead')}
          className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
            activeTab === 'lead'
              ? 'bg-card border border-border shadow-sm'
              : 'hover:bg-muted/50'
          }`}
        >
          <span>👥</span>
          <span>리드 리마인더</span>
          {leadAlertCount > 0 && (
            <span className="px-1.5 py-0.5 bg-yellow-500 text-black rounded-full text-[10px]">
              {leadAlertCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('kei')}
          className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
            activeTab === 'kei'
              ? 'bg-card border border-border shadow-sm'
              : 'hover:bg-muted/50'
          }`}
        >
          <TrendingUp className="w-3 h-3" />
          <span>KEI 키워드</span>
          {keiAlertCount > 0 && (
            <span className="px-1.5 py-0.5 bg-blue-500 text-white rounded-full text-[10px]">
              {keiAlertCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('approval')}
          className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
            activeTab === 'approval'
              ? 'bg-card border border-border shadow-sm'
              : 'hover:bg-muted/50'
          }`}
        >
          <CheckCircle className="w-3 h-3" />
          <span>자동 승인</span>
          {approvalAlertCount > 0 && (
            <span className="px-1.5 py-0.5 bg-green-500 text-white rounded-full text-[10px]">
              {approvalAlertCount}
            </span>
          )}
        </button>
      </div>

      {/* 순위 알림 탭 */}
      {activeTab === 'rank' && rankData && rankAlertCount > 0 && (
        <div className="space-y-3">
          {/* Critical Drops */}
          {rankData.critical_drops.length > 0 && (
            <div>
              <p className="text-xs text-red-500 dark:text-red-400 mb-2">
                🔴 5위 이상 하락 ({rankData.critical_drops.length}개)
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {rankData.critical_drops.slice(0, 4).map((drop) => (
                  <div
                    key={drop.keyword}
                    className="flex items-center justify-between bg-red-500/20 px-3 py-2 rounded-lg"
                  >
                    <span className="font-medium text-sm truncate max-w-[60%]">{drop.keyword}</span>
                    <div className="text-right">
                      <span className="text-xs text-muted-foreground">
                        {drop.previous_rank}위 → {drop.current_rank}위
                      </span>
                      <span className="ml-2 text-sm font-bold text-red-600 dark:text-red-400">
                        ↓{drop.rank_change}위
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warnings */}
          {rankData.warnings.length > 0 && (
            <div>
              <p className="text-xs text-yellow-600 dark:text-yellow-400 mb-2">
                🟡 3위 이상 하락 ({rankData.warnings.length}개)
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {rankData.warnings.slice(0, 4).map((warn) => (
                  <div
                    key={warn.keyword}
                    className="flex items-center justify-between bg-yellow-500/20 px-3 py-2 rounded-lg"
                  >
                    <span className="font-medium text-sm truncate max-w-[60%]">{warn.keyword}</span>
                    <div className="text-right">
                      <span className="text-xs text-muted-foreground">
                        {warn.previous_rank}위 → {warn.current_rank}위
                      </span>
                      <span className="ml-2 text-sm font-bold text-yellow-600 dark:text-yellow-400">
                        ↓{warn.rank_change}위
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 바로가기 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/battle')}
            icon={<ArrowRight className="w-4 h-4" />}
            iconPosition="right"
          >
            순위 현황 보기
          </Button>
        </div>
      )}

      {activeTab === 'rank' && rankError && (
        <div className="text-center py-4">
          <p className="text-sm text-red-500 mb-2">❌ 순위 알림을 불러올 수 없습니다</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => refetchRank()}
            icon={<RefreshCw className="w-3 h-3" />}
          >
            다시 시도
          </Button>
        </div>
      )}

      {activeTab === 'rank' && !rankError && rankAlertCount === 0 && (
        <div className="text-center py-4 text-muted-foreground text-sm">
          ✅ 순위 변동 알림이 없습니다
        </div>
      )}

      {/* 리드 알림 탭 */}
      {activeTab === 'lead' && leadData && leadAlertCount > 0 && (
        <div className="space-y-3">
          {/* 팔로업 기한 초과 */}
          {leadData.overdue_followups.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">
                📅 팔로업 기한 초과 ({leadData.overdue_followups.length}건)
              </p>
              <div className="flex flex-wrap gap-2">
                {leadData.overdue_followups.slice(0, 3).map((lead) => (
                  <Button
                    key={lead.id}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate(`/leads?id=${lead.id}`)}
                    className="px-3 py-1.5 bg-red-500/20 text-red-600 dark:text-red-400 hover:bg-red-500/30 flex items-center gap-1"
                  >
                    <span>{platformIcons[lead.platform] || '📱'}</span>
                    <span className="max-w-[120px] truncate">{lead.title}</span>
                    <span className="text-red-400">D+{lead.days_overdue}</span>
                  </Button>
                ))}
                {leadData.overdue_followups.length > 3 && (
                  <span className="text-xs text-muted-foreground self-center">
                    +{leadData.overdue_followups.length - 3}개
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 오래된 pending 리드 */}
          {leadData.stale_leads.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">
                ⚠️ 대기 중 3일 이상 ({leadData.stale_leads.length}건)
              </p>
              <div className="flex flex-wrap gap-2">
                {leadData.stale_leads.slice(0, 3).map((lead) => (
                  <Button
                    key={lead.id}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate(`/leads?id=${lead.id}`)}
                    className="px-3 py-1.5 bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/30 flex items-center gap-1"
                  >
                    <span>{platformIcons[lead.platform] || '📱'}</span>
                    <span className="max-w-[120px] truncate">{lead.title}</span>
                  </Button>
                ))}
                {leadData.stale_leads.length > 3 && (
                  <span className="text-xs text-muted-foreground self-center">
                    +{leadData.stale_leads.length - 3}개
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 응답 없는 리드 */}
          {leadData.no_response_leads.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">
                📭 연락 후 응답 없음 ({leadData.no_response_leads.length}건)
              </p>
              <div className="flex flex-wrap gap-2">
                {leadData.no_response_leads.slice(0, 3).map((lead) => (
                  <Button
                    key={lead.id}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate(`/leads?id=${lead.id}`)}
                    className="px-3 py-1.5 bg-orange-500/20 text-orange-600 dark:text-orange-400 hover:bg-orange-500/30 flex items-center gap-1"
                  >
                    <span>{platformIcons[lead.platform] || '📱'}</span>
                    <span className="max-w-[120px] truncate">{lead.title}</span>
                  </Button>
                ))}
                {leadData.no_response_leads.length > 3 && (
                  <span className="text-xs text-muted-foreground self-center">
                    +{leadData.no_response_leads.length - 3}개
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 바로가기 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/leads')}
            icon={<ArrowRight className="w-4 h-4" />}
            iconPosition="right"
          >
            전체 리드 보기
          </Button>
        </div>
      )}

      {activeTab === 'lead' && leadError && (
        <div className="text-center py-4">
          <p className="text-sm text-red-500 mb-2">❌ 리드 알림을 불러올 수 없습니다</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => refetchLead()}
            icon={<RefreshCw className="w-3 h-3" />}
          >
            다시 시도
          </Button>
        </div>
      )}

      {activeTab === 'lead' && !leadError && leadAlertCount === 0 && (
        <div className="text-center py-4 text-muted-foreground text-sm">
          ✅ 리드 리마인더가 없습니다
        </div>
      )}

      {/* [Phase 6.2] KEI 알림 탭 */}
      {activeTab === 'kei' && keiData && keiAlertCount > 0 && (
        <div className="space-y-3">
          {/* 새 고KEI 키워드 */}
          {keiData.new_high_kei.length > 0 && (
            <div>
              <p className="text-xs text-blue-500 mb-2 flex items-center gap-1">
                <Zap className="w-3 h-3" />
                새로 발견된 고효율 키워드 ({keiData.new_high_kei.length}개)
              </p>
              <div className="flex flex-wrap gap-2">
                {keiData.new_high_kei.slice(0, 4).map((kw) => (
                  <Button
                    key={kw.keyword}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate('/pathfinder')}
                    className="px-3 py-1.5 bg-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-500/30 flex items-center gap-1"
                  >
                    <span className="max-w-[100px] truncate">{kw.keyword}</span>
                    <span className="font-bold">KEI {kw.kei.toFixed(0)}</span>
                  </Button>
                ))}
                {keiData.new_high_kei.length > 4 && (
                  <span className="text-xs text-muted-foreground self-center">
                    +{keiData.new_high_kei.length - 4}개
                  </span>
                )}
              </div>
            </div>
          )}

          {/* S급 KEI 키워드 */}
          {keiData.s_grade_kei.length > 0 && (
            <div>
              <p className="text-xs text-green-500 mb-2 flex items-center gap-1">
                <TrendingUp className="w-3 h-3" />
                S급 KEI 키워드 ({keiData.s_grade_kei.length}개)
              </p>
              <div className="flex flex-wrap gap-2">
                {keiData.s_grade_kei.slice(0, 3).map((kw) => (
                  <span
                    key={kw.keyword}
                    className="px-3 py-1.5 text-xs bg-gradient-to-r from-yellow-400/20 to-amber-500/20 text-amber-600 dark:text-amber-400 rounded-lg flex items-center gap-1"
                  >
                    <Zap className="w-3 h-3" />
                    <span className="max-w-[100px] truncate">{kw.keyword}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 공략 기회 키워드 */}
          {keiData.opportunities.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">
                🎯 공략 기회 ({keiData.opportunities.length}개)
              </p>
              <div className="flex flex-wrap gap-2">
                {keiData.opportunities.slice(0, 3).map((kw) => (
                  <span
                    key={kw.keyword}
                    className="px-2 py-1 text-xs bg-muted rounded-lg"
                  >
                    {kw.keyword}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 바로가기 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/pathfinder')}
            icon={<ArrowRight className="w-4 h-4" />}
            iconPosition="right"
          >
            Pathfinder에서 보기
          </Button>
        </div>
      )}

      {activeTab === 'kei' && keiError && (
        <div className="text-center py-4">
          <p className="text-sm text-red-500 mb-2">❌ KEI 알림을 불러올 수 없습니다</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => refetchKei()}
            icon={<RefreshCw className="w-3 h-3" />}
          >
            다시 시도
          </Button>
        </div>
      )}

      {activeTab === 'kei' && !keiError && keiAlertCount === 0 && (
        <div className="text-center py-4 text-muted-foreground text-sm">
          ✅ KEI 관련 알림이 없습니다
        </div>
      )}

      {/* [Phase 6.2] 자동 승인 알림 탭 */}
      {activeTab === 'approval' && approvalData && approvalAlertCount > 0 && (
        <div className="space-y-3">
          {/* 자동 승인된 항목 */}
          {approvalData.auto_approved.length > 0 && (
            <div>
              <p className="text-xs text-green-500 mb-2 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" />
                자동 승인됨 ({approvalData.auto_approved.length}건)
              </p>
              <div className="flex flex-wrap gap-2">
                {approvalData.auto_approved.slice(0, 4).map((item) => (
                  <Button
                    key={item.id}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate('/viral')}
                    className="px-3 py-1.5 bg-green-500/20 text-green-600 dark:text-green-400 hover:bg-green-500/30 flex items-center gap-1"
                  >
                    <span>{platformIcons[item.platform] || '📱'}</span>
                    <span className="max-w-[100px] truncate">{item.title}</span>
                  </Button>
                ))}
                {approvalData.auto_approved.length > 4 && (
                  <span className="text-xs text-muted-foreground self-center">
                    +{approvalData.auto_approved.length - 4}개
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 수동 검토 필요 */}
          {approvalData.pending_review.length > 0 && (
            <div>
              <p className="text-xs text-yellow-500 mb-2">
                ⚠️ 수동 검토 필요 ({approvalData.pending_review.length}건)
              </p>
              <div className="flex flex-wrap gap-2">
                {approvalData.pending_review.slice(0, 3).map((item) => (
                  <Button
                    key={item.id}
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate('/viral')}
                    className="px-3 py-1.5 bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/30 flex items-center gap-1"
                  >
                    <span>{platformIcons[item.platform] || '📱'}</span>
                    <span className="max-w-[100px] truncate">{item.title}</span>
                    <span className="text-yellow-400">점수 {item.priority_score}</span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* 활성 규칙 수 */}
          <div className="text-xs text-muted-foreground">
            활성화된 자동 승인 규칙: {approvalData.active_rules.length}개
          </div>

          {/* 바로가기 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/agent')}
            icon={<ArrowRight className="w-4 h-4" />}
            iconPosition="right"
          >
            규칙 관리하기
          </Button>
        </div>
      )}

      {activeTab === 'approval' && approvalError && (
        <div className="text-center py-4">
          <p className="text-sm text-red-500 mb-2">❌ 자동 승인 알림을 불러올 수 없습니다</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => refetchApproval()}
            icon={<RefreshCw className="w-3 h-3" />}
          >
            다시 시도
          </Button>
        </div>
      )}

      {activeTab === 'approval' && !approvalError && approvalAlertCount === 0 && (
        <div className="text-center py-4 text-muted-foreground text-sm">
          ✅ 자동 승인 관련 알림이 없습니다
        </div>
      )}
    </div>
  )
}
