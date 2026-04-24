/**
 * [Phase F-3] 연관 정보 사이드바
 * 선택된 항목의 관련 데이터를 슬라이드 패널로 표시
 */

import { useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  X,
  Target,
  TrendingUp,
  MessageSquare,
  User,
  ExternalLink,
  Loader2,
  BarChart3,
  Link2,
  ArrowRight,
} from 'lucide-react'
import { pathfinderApi, battleApi, viralApi, leadsApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

// 컨텍스트 타입 정의
interface KeywordContext {
  type: 'keyword'
  keyword: string
}

interface LeadContext {
  type: 'lead'
  leadId: number
  sourceKeyword?: string
  platform?: string
}

interface ViralContext {
  type: 'viral'
  viralId: number
  matchedKeyword?: string
  platform?: string
}

export type SidebarContext = KeywordContext | LeadContext | ViralContext | null

interface RelatedInfoSidebarProps {
  context: SidebarContext
  onClose: () => void
  /** 키워드 허브 열기 (선택적) */
  onOpenKeywordHub?: (keyword: string) => void
}

export default function RelatedInfoSidebar({
  context,
  onClose,
  onOpenKeywordHub,
}: RelatedInfoSidebarProps) {
  const navigate = useNavigate()

  // ESC 키로 닫기
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose()
    }
  }, [onClose])

  useEffect(() => {
    if (context) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [context, handleKeyDown])

  if (!context) return null

  return (
    <>
      {/* 오버레이 */}
      <div
        className="fixed inset-0 bg-black/30 z-40 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 사이드바 */}
      <div
        className="fixed right-0 top-0 bottom-0 w-96 bg-card border-l border-border z-50 shadow-xl overflow-y-auto animate-sidebar-slide-in"
        role="dialog"
        aria-label="연관 정보"
      >
        {/* 헤더 */}
        <div className="sticky top-0 bg-card border-b border-border p-4 flex items-center justify-between z-10">
          <h3 className="font-semibold flex items-center gap-2">
            <Link2 className="w-5 h-5 text-primary" />
            연관 정보
          </h3>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            title="닫기"
            aria-label="닫기"
          />
        </div>

        {/* 컨텐츠 */}
        <div className="p-4">
          {context.type === 'keyword' && (
            <KeywordRelatedInfo
              keyword={context.keyword}
              navigate={navigate}
              onOpenKeywordHub={onOpenKeywordHub}
            />
          )}
          {context.type === 'lead' && (
            <LeadRelatedInfo
              leadId={context.leadId}
              sourceKeyword={context.sourceKeyword}
              platform={context.platform}
              navigate={navigate}
              onOpenKeywordHub={onOpenKeywordHub}
            />
          )}
          {context.type === 'viral' && (
            <ViralRelatedInfo
              viralId={context.viralId}
              matchedKeyword={context.matchedKeyword}
              platform={context.platform}
              navigate={navigate}
              onOpenKeywordHub={onOpenKeywordHub}
            />
          )}
        </div>
      </div>
    </>
  )
}

// 키워드 연관 정보
function KeywordRelatedInfo({
  keyword,
  navigate,
  onOpenKeywordHub,
}: {
  keyword: string
  navigate: ReturnType<typeof useNavigate>
  onOpenKeywordHub?: (keyword: string) => void
}) {
  // 키워드 인사이트
  const { data: keywordData, isLoading: keywordLoading } = useQuery({
    queryKey: ['sidebar-keyword', keyword],
    queryFn: async () => {
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) =>
        k.keyword.toLowerCase() === keyword.toLowerCase()
      )
    },
    enabled: !!keyword,
  })

  // 순위 정보
  const { data: rankData, isLoading: rankLoading } = useQuery({
    queryKey: ['sidebar-rank', keyword],
    queryFn: async () => {
      const keywords = await battleApi.getRankingKeywords()
      return (keywords || []).find((k: any) =>
        k.keyword.toLowerCase() === keyword.toLowerCase()
      )
    },
    enabled: !!keyword,
  })

  // 바이럴 정보
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['sidebar-viral', keyword],
    queryFn: async () => {
      const data = await viralApi.getTargets('', undefined, 20, { search: keyword })
      const targets = data?.targets || []
      return targets.filter((t: any) =>
        t.matched_keyword?.toLowerCase().includes(keyword.toLowerCase())
      ).slice(0, 5)
    },
    enabled: !!keyword,
  })

  // 리드 정보
  const { data: leadData, isLoading: leadLoading } = useQuery({
    queryKey: ['sidebar-leads', keyword],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 50 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 50 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      return allLeads.filter((l: any) =>
        l.source_keyword?.toLowerCase().includes(keyword.toLowerCase())
      ).slice(0, 5)
    },
    enabled: !!keyword,
  })

  const isLoading = keywordLoading || rankLoading || viralLoading || leadLoading

  return (
    <div className="space-y-4">
      {/* 키워드 헤더 */}
      <div className="bg-primary/5 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">키워드</span>
          {onOpenKeywordHub && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => onOpenKeywordHub(keyword)}
              icon={<ArrowRight className="w-3 h-3" />}
              iconPosition="right"
            >
              상세 Hub
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-primary" />
          <span className="font-bold text-lg">{keyword}</span>
          {keywordData?.grade && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              keywordData.grade === 'S' ? 'bg-red-500/20 text-red-500' :
              keywordData.grade === 'A' ? 'bg-green-500/20 text-green-500' :
              keywordData.grade === 'B' ? 'bg-blue-500/20 text-blue-500' :
              'bg-muted text-muted-foreground'
            }`}>
              {keywordData.grade}급
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <>
          {/* 키워드 상세 */}
          {keywordData && (
            <InfoSection
              icon={<BarChart3 className="w-4 h-4" />}
              title="키워드 인사이트"
            >
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="bg-muted/50 rounded p-2">
                  <div className="text-[10px] text-muted-foreground">검색량</div>
                  <div className="font-medium">{keywordData.search_volume?.toLocaleString() || '-'}</div>
                </div>
                <div className="bg-muted/50 rounded p-2">
                  <div className="text-[10px] text-muted-foreground">문서수</div>
                  <div className="font-medium">{keywordData.document_count?.toLocaleString() || '-'}</div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(keyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                Pathfinder에서 보기
              </Button>
            </InfoSection>
          )}

          {/* 순위 정보 */}
          {rankData && (
            <InfoSection
              icon={<TrendingUp className="w-4 h-4" />}
              title="순위 추적"
            >
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">현재 순위</span>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg">{rankData.current_rank}위</span>
                  {rankData.rank_change !== 0 && (
                    <span className={`text-xs ${
                      rankData.rank_change > 0 ? 'text-green-500' : 'text-red-500'
                    }`}>
                      {rankData.rank_change > 0 ? '▲' : '▼'}{Math.abs(rankData.rank_change)}
                    </span>
                  )}
                </div>
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/battle?keyword=${encodeURIComponent(keyword)}&tab=trends`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                Battle Intelligence에서 보기
              </Button>
            </InfoSection>
          )}

          {/* 바이럴 목록 */}
          {viralData && viralData.length > 0 && (
            <InfoSection
              icon={<MessageSquare className="w-4 h-4" />}
              title={`관련 바이럴 (${viralData.length})`}
            >
              <div className="space-y-2">
                {viralData.map((v: any) => (
                  <div key={v.id} className="text-xs bg-muted/50 rounded p-2">
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        v.status === 'completed' ? 'bg-green-500/20 text-green-500' :
                        v.status === 'pending' ? 'bg-yellow-500/20 text-yellow-500' :
                        'bg-muted'
                      }`}>
                        {v.status}
                      </span>
                      <span>{v.platform}</span>
                    </div>
                    <div className="truncate">{v.title}</div>
                  </div>
                ))}
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/viral?search=${encodeURIComponent(keyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                Viral Hunter에서 보기
              </Button>
            </InfoSection>
          )}

          {/* 리드 목록 */}
          {leadData && leadData.length > 0 && (
            <InfoSection
              icon={<User className="w-4 h-4" />}
              title={`관련 리드 (${leadData.length})`}
            >
              <div className="space-y-2">
                {leadData.map((l: any) => (
                  <div key={l.id} className="text-xs bg-muted/50 rounded p-2">
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        l.grade === 'hot' ? 'bg-red-500/20 text-red-500' :
                        l.grade === 'warm' ? 'bg-yellow-500/20 text-yellow-500' :
                        'bg-blue-500/20 text-blue-500'
                      }`}>
                        {l.grade || 'cold'}
                      </span>
                      <span>{l.platform}</span>
                    </div>
                    <div className="truncate">{l.title}</div>
                  </div>
                ))}
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/leads?keyword=${encodeURIComponent(keyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                Lead Manager에서 보기
              </Button>
            </InfoSection>
          )}
        </>
      )}
    </div>
  )
}

// 리드 연관 정보
function LeadRelatedInfo({
  leadId,
  sourceKeyword,
  platform,
  navigate,
  onOpenKeywordHub,
}: {
  leadId: number
  sourceKeyword?: string
  platform?: string
  navigate: ReturnType<typeof useNavigate>
  onOpenKeywordHub?: (keyword: string) => void
}) {
  // 소스 키워드 정보
  const { data: keywordData, isLoading: keywordLoading } = useQuery({
    queryKey: ['sidebar-lead-keyword', sourceKeyword],
    queryFn: async () => {
      if (!sourceKeyword) return null
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) =>
        k.keyword.toLowerCase() === sourceKeyword.toLowerCase()
      )
    },
    enabled: !!sourceKeyword,
  })

  // 같은 소스 키워드의 다른 리드
  const { data: relatedLeads, isLoading: leadsLoading } = useQuery({
    queryKey: ['sidebar-related-leads', sourceKeyword],
    queryFn: async () => {
      if (!sourceKeyword) return []
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 50 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 50 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      return allLeads.filter((l: any) =>
        l.source_keyword?.toLowerCase() === sourceKeyword.toLowerCase() &&
        l.id !== leadId
      ).slice(0, 5)
    },
    enabled: !!sourceKeyword,
  })

  const isLoading = keywordLoading || leadsLoading

  return (
    <div className="space-y-4">
      {/* 리드 헤더 */}
      <div className="bg-primary/5 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">리드 #{leadId}</span>
          <span className="text-xs text-muted-foreground">{platform}</span>
        </div>
        {sourceKeyword ? (
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">소스 키워드:</span>
            <Button
              variant="ghost"
              size="xs"
              onClick={() => onOpenKeywordHub?.(sourceKeyword)}
              className="font-medium"
            >
              {sourceKeyword}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">소스 키워드 정보 없음</p>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && sourceKeyword && (
        <>
          {/* 키워드 상세 */}
          {keywordData && (
            <InfoSection
              icon={<Target className="w-4 h-4" />}
              title="소스 키워드 정보"
            >
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-muted-foreground">등급</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  keywordData.grade === 'S' ? 'bg-red-500/20 text-red-500' :
                  keywordData.grade === 'A' ? 'bg-green-500/20 text-green-500' :
                  'bg-muted'
                }`}>
                  {keywordData.grade}급
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">검색량</span>
                <span className="font-medium">{keywordData.search_volume?.toLocaleString() || '-'}</span>
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(sourceKeyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                키워드 상세 보기
              </Button>
            </InfoSection>
          )}

          {/* 관련 리드 */}
          {relatedLeads && relatedLeads.length > 0 && (
            <InfoSection
              icon={<User className="w-4 h-4" />}
              title={`같은 키워드 리드 (${relatedLeads.length})`}
            >
              <div className="space-y-2">
                {relatedLeads.map((l: any) => (
                  <div key={l.id} className="text-xs bg-muted/50 rounded p-2">
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        l.grade === 'hot' ? 'bg-red-500/20 text-red-500' :
                        l.grade === 'warm' ? 'bg-yellow-500/20 text-yellow-500' :
                        'bg-blue-500/20 text-blue-500'
                      }`}>
                        {l.grade || 'cold'}
                      </span>
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        l.status === 'converted' ? 'bg-green-500/20 text-green-500' :
                        l.status === 'contacted' ? 'bg-blue-500/20 text-blue-500' :
                        'bg-muted'
                      }`}>
                        {l.status}
                      </span>
                    </div>
                    <div className="truncate">{l.title}</div>
                  </div>
                ))}
              </div>
            </InfoSection>
          )}
        </>
      )}
    </div>
  )
}

// 바이럴 연관 정보
function ViralRelatedInfo({
  viralId,
  matchedKeyword,
  platform,
  navigate,
  onOpenKeywordHub,
}: {
  viralId: number
  matchedKeyword?: string
  platform?: string
  navigate: ReturnType<typeof useNavigate>
  onOpenKeywordHub?: (keyword: string) => void
}) {
  // 매칭 키워드 정보
  const { data: keywordData, isLoading: keywordLoading } = useQuery({
    queryKey: ['sidebar-viral-keyword', matchedKeyword],
    queryFn: async () => {
      if (!matchedKeyword) return null
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) =>
        k.keyword.toLowerCase() === matchedKeyword.toLowerCase()
      )
    },
    enabled: !!matchedKeyword,
  })

  // 같은 키워드의 다른 바이럴
  const { data: relatedVirals, isLoading: viralsLoading } = useQuery({
    queryKey: ['sidebar-related-virals', matchedKeyword],
    queryFn: async () => {
      if (!matchedKeyword) return []
      const data = await viralApi.getTargets('', undefined, 20, { search: matchedKeyword })
      const targets = data?.targets || []
      return targets.filter((t: any) =>
        t.matched_keyword?.toLowerCase() === matchedKeyword.toLowerCase() &&
        t.id !== viralId
      ).slice(0, 5)
    },
    enabled: !!matchedKeyword,
  })

  const isLoading = keywordLoading || viralsLoading

  return (
    <div className="space-y-4">
      {/* 바이럴 헤더 */}
      <div className="bg-primary/5 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">바이럴 #{viralId}</span>
          <span className="text-xs text-muted-foreground">{platform}</span>
        </div>
        {matchedKeyword ? (
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">매칭 키워드:</span>
            <Button
              variant="ghost"
              size="xs"
              onClick={() => onOpenKeywordHub?.(matchedKeyword)}
              className="font-medium"
            >
              {matchedKeyword}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">매칭 키워드 정보 없음</p>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && matchedKeyword && (
        <>
          {/* 키워드 상세 */}
          {keywordData && (
            <InfoSection
              icon={<Target className="w-4 h-4" />}
              title="매칭 키워드 정보"
            >
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-muted-foreground">등급</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  keywordData.grade === 'S' ? 'bg-red-500/20 text-red-500' :
                  keywordData.grade === 'A' ? 'bg-green-500/20 text-green-500' :
                  'bg-muted'
                }`}>
                  {keywordData.grade}급
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">검색량</span>
                <span className="font-medium">{keywordData.search_volume?.toLocaleString() || '-'}</span>
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(matchedKeyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                키워드 상세 보기
              </Button>
            </InfoSection>
          )}

          {/* 관련 바이럴 */}
          {relatedVirals && relatedVirals.length > 0 && (
            <InfoSection
              icon={<MessageSquare className="w-4 h-4" />}
              title={`같은 키워드 바이럴 (${relatedVirals.length})`}
            >
              <div className="space-y-2">
                {relatedVirals.map((v: any) => (
                  <div key={v.id} className="text-xs bg-muted/50 rounded p-2">
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        v.status === 'completed' ? 'bg-green-500/20 text-green-500' :
                        v.status === 'pending' ? 'bg-yellow-500/20 text-yellow-500' :
                        'bg-muted'
                      }`}>
                        {v.status}
                      </span>
                      <span>{v.platform}</span>
                    </div>
                    <div className="truncate">{v.title}</div>
                  </div>
                ))}
              </div>
              <Button
                variant="ghost"
                size="xs"
                fullWidth
                onClick={() => navigate(`/viral?keyword=${encodeURIComponent(matchedKeyword)}`)}
                icon={<ExternalLink className="w-3 h-3" />}
                iconPosition="right"
                className="mt-2"
              >
                Viral Hunter에서 보기
              </Button>
            </InfoSection>
          )}
        </>
      )}
    </div>
  )
}

// 정보 섹션 컴포넌트
function InfoSection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="border border-border rounded-lg p-3">
      <h4 className="text-sm font-medium mb-3 flex items-center gap-2 text-muted-foreground">
        {icon}
        {title}
      </h4>
      {children}
    </div>
  )
}
