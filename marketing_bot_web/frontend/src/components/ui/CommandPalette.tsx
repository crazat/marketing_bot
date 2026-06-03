import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, Command, ArrowRight, Loader2, TrendingUp, MessageSquare, Users, Target, Clock, BarChart3, Flame, Swords, ClipboardList, Eye, Settings, RefreshCw, Radio, Telescope } from 'lucide-react'

const CMD_ICON = 'w-4 h-4'
import { pathfinderApi, battleApi, viralApi, leadsApi, hudApi } from '@/services/api'
import { useRecentItems, type RecentItem } from '@/hooks/useRecentItems'
import { useToast } from '@/components/ui/Toast'

interface CommandItem {
  id: string
  icon: string | React.ReactNode
  label: string
  description: string
  action: () => void
  keywords?: string[]
  category: 'navigation' | 'action' | 'search' | 'keyword-result'
  metadata?: {
    rank?: number
    viral?: number
    leads?: number
    grade?: string
  }
}

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  onOpenKeywordHub?: (keyword: string) => void
}

export default function CommandPalette({ isOpen, onClose, onOpenKeywordHub }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()
  const toast = useToast()
  const { items: recentItems } = useRecentItems()

  // [Phase E-3] 키워드 검색 (3자 이상일 때만)
  const searchEnabled = query.trim().length >= 3

  // 키워드 인사이트 검색
  const { data: keywordData, isLoading: keywordLoading } = useQuery({
    queryKey: ['cmd-keyword', query],
    queryFn: async () => {
      const data = await pathfinderApi.getKeywords({ limit: 100 })
      const keywords = data?.keywords || []
      return keywords.filter((k: any) =>
        k.keyword?.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 5)
    },
    enabled: isOpen && searchEnabled,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 순위 키워드 검색
  const { data: rankData, isLoading: rankLoading } = useQuery({
    queryKey: ['cmd-rank', query],
    queryFn: async () => {
      const keywords = await battleApi.getRankingKeywords()
      return (keywords || []).filter((k: any) =>
        k.keyword?.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 3)
    },
    enabled: isOpen && searchEnabled,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 바이럴 검색 — getTargets는 array를 반환
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['cmd-viral', query],
    queryFn: async () => {
      const data = await viralApi.getTargets('', undefined, 10, { search: query })
      return Array.isArray(data) ? data.slice(0, 5) : []
    },
    enabled: isOpen && searchEnabled,
    staleTime: 60000,
  })

  // 리드 검색
  const { data: leadsResult, isLoading: leadsResultLoading } = useQuery({
    queryKey: ['cmd-leads', query],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 50 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 50 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      return allLeads.filter((l: any) =>
        l.title?.toLowerCase().includes(query.toLowerCase()) ||
        l.source_keyword?.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 3)
    },
    enabled: isOpen && searchEnabled,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  const isSearching = keywordLoading || rankLoading || viralLoading || leadsResultLoading

  // 정적 명령어 목록
  const staticCommands: CommandItem[] = useMemo(() => [
    // 네비게이션
    {
      id: 'nav-dashboard',
      icon: <BarChart3 className={CMD_ICON} strokeWidth={1.7} />,
      label: '대시보드',
      description: '메인 대시보드로 이동',
      action: () => { navigate('/'); onClose() },
      keywords: ['dashboard', 'home', '홈', '메인'],
      category: 'navigation'
    },
    {
      id: 'nav-pathfinder',
      icon: <Target className={CMD_ICON} strokeWidth={1.7} />,
      label: 'Pathfinder',
      description: '키워드 발굴 도구',
      action: () => { navigate('/pathfinder'); onClose() },
      keywords: ['keyword', '키워드', '발굴', 'seo'],
      category: 'navigation'
    },
    {
      id: 'nav-viral',
      icon: <Flame className={CMD_ICON} strokeWidth={1.7} />,
      label: 'Viral Hunter',
      description: '바이럴 콘텐츠 수집',
      action: () => { navigate('/viral'); onClose() },
      keywords: ['viral', '바이럴', '콘텐츠', '댓글'],
      category: 'navigation'
    },
    {
      id: 'nav-battle',
      icon: <Swords className={CMD_ICON} strokeWidth={1.7} />,
      label: 'Battle Intelligence',
      description: '순위 추적 및 경쟁 분석',
      action: () => { navigate('/battle'); onClose() },
      keywords: ['rank', '순위', 'battle', '경쟁', '분석'],
      category: 'navigation'
    },
    {
      id: 'nav-leads',
      icon: <ClipboardList className={CMD_ICON} strokeWidth={1.7} />,
      label: 'Lead Manager',
      description: '리드 관리',
      action: () => { navigate('/leads'); onClose() },
      keywords: ['lead', '리드', '고객', '잠재고객'],
      category: 'navigation'
    },
    {
      id: 'nav-competitors',
      icon: <Eye className={CMD_ICON} strokeWidth={1.7} />,
      label: '경쟁사 분석',
      description: '경쟁사 약점 분석',
      action: () => { navigate('/competitors'); onClose() },
      keywords: ['competitor', '경쟁사', '약점'],
      category: 'navigation'
    },
    {
      id: 'nav-qa',
      icon: <MessageSquare className={CMD_ICON} strokeWidth={1.7} />,
      label: 'Q&A Repository',
      description: 'Q&A 패턴 관리',
      action: () => { navigate('/qa'); onClose() },
      keywords: ['qa', 'question', 'answer', '질문', '응답'],
      category: 'navigation'
    },
    {
      id: 'nav-settings',
      icon: <Settings className={CMD_ICON} strokeWidth={1.7} />,
      label: '설정',
      description: '시스템 설정',
      action: () => { navigate('/settings'); onClose() },
      keywords: ['settings', '설정', 'config'],
      category: 'navigation'
    },

    // 액션
    {
      id: 'action-refresh',
      icon: <RefreshCw className={CMD_ICON} strokeWidth={1.7} />,
      label: '새로고침',
      description: '현재 페이지 새로고침',
      action: () => { window.location.reload() },
      keywords: ['refresh', 'reload', '새로고침'],
      category: 'action'
    },
    {
      id: 'action-scan-rank',
      icon: <Radio className={CMD_ICON} strokeWidth={1.7} />,
      label: '순위 스캔 실행',
      description: 'Place Sniper 실행',
      action: async () => {
        setIsLoading(true)
        try {
          await hudApi.executeMission('place_sniper')
          toast.success('순위 스캔이 시작되었습니다.')
        } catch {
          toast.error('스캔 실행에 실패했습니다.')
        } finally {
          setIsLoading(false)
          onClose()
        }
      },
      keywords: ['scan', '스캔', '순위체크'],
      category: 'action'
    },
    {
      id: 'action-pathfinder-run',
      icon: <Telescope className={CMD_ICON} strokeWidth={1.7} />,
      label: '키워드 발굴 실행',
      description: 'Pathfinder 스캔 시작',
      action: async () => {
        setIsLoading(true)
        try {
          await pathfinderApi.runPathfinder('legion', 500, true)
          toast.success('키워드 발굴이 시작되었습니다.')
        } catch {
          toast.error('발굴 실행에 실패했습니다.')
        } finally {
          setIsLoading(false)
          onClose()
        }
      },
      keywords: ['pathfinder', '발굴', 'discover'],
      category: 'action'
    },
  ], [navigate, onClose, toast])

  // [Phase E-3] 동적 키워드 검색 결과를 명령어로 변환
  const keywordCommands: CommandItem[] = useMemo(() => {
    if (!searchEnabled) return []

    const commands: CommandItem[] = []

    // 키워드 인사이트 결과
    keywordData?.forEach((kw: any) => {
      // 순위 정보 찾기
      const rankInfo = rankData?.find((r: any) => r.keyword === kw.keyword)
      // 바이럴 수
      const viralCount = viralData?.filter((v: any) =>
        v.matched_keyword?.toLowerCase().includes(kw.keyword.toLowerCase())
      ).length || 0
      // 리드 수
      const leadCount = leadsResult?.filter((l: any) =>
        l.source_keyword?.toLowerCase().includes(kw.keyword.toLowerCase())
      ).length || 0

      commands.push({
        id: `kw-${kw.keyword}`,
        icon: <Target className="w-5 h-5 text-primary" />,
        label: kw.keyword,
        description: `${kw.grade || '-'}급 · 검색량 ${kw.search_volume?.toLocaleString() || '-'}${rankInfo ? ` · 순위 ${rankInfo.current_rank}위` : ''}`,
        action: () => {
          if (onOpenKeywordHub) {
            onOpenKeywordHub(kw.keyword)
          } else {
            navigate(`/pathfinder?keyword=${encodeURIComponent(kw.keyword)}`)
          }
          onClose()
        },
        category: 'keyword-result',
        metadata: {
          rank: rankInfo?.current_rank,
          viral: viralCount,
          leads: leadCount,
          grade: kw.grade,
        }
      })
    })

    // 순위 추적 중이지만 인사이트에 없는 키워드
    rankData?.forEach((rk: any) => {
      if (!commands.find(c => c.id === `kw-${rk.keyword}`)) {
        commands.push({
          id: `rank-${rk.keyword}`,
          icon: <TrendingUp className="w-5 h-5 text-purple-500" />,
          label: rk.keyword,
          description: `순위 추적 중 · ${rk.current_rank}위 ${rk.rank_change > 0 ? '▲' : rk.rank_change < 0 ? '▼' : ''}${Math.abs(rk.rank_change) || ''}`,
          action: () => {
            navigate(`/battle?keyword=${encodeURIComponent(rk.keyword)}&tab=trends`)
            onClose()
          },
          category: 'keyword-result',
          metadata: {
            rank: rk.current_rank,
          }
        })
      }
    })

    return commands
  }, [searchEnabled, keywordData, rankData, viralData, leadsResult, navigate, onClose, onOpenKeywordHub])

  // 바이럴 검색 결과
  const viralCommands: CommandItem[] = useMemo(() => {
    if (!searchEnabled || !viralData?.length) return []

    return viralData.slice(0, 2).map((v: any) => ({
      id: `viral-${v.id}`,
      icon: <MessageSquare className="w-5 h-5 text-orange-500" />,
      label: v.title?.slice(0, 40) + (v.title?.length > 40 ? '...' : ''),
      description: `${v.platform} · ${v.status}`,
      action: () => {
        navigate(`/viral?search=${encodeURIComponent(query)}`)
        onClose()
      },
      category: 'keyword-result' as const,
    }))
  }, [searchEnabled, viralData, query, navigate, onClose])

  // 리드 검색 결과
  const leadCommands: CommandItem[] = useMemo(() => {
    if (!searchEnabled || !leadsResult?.length) return []

    return leadsResult.slice(0, 2).map((l: any) => ({
      id: `lead-${l.id}`,
      icon: <Users className="w-5 h-5 text-green-500" />,
      label: l.title?.slice(0, 40) + (l.title?.length > 40 ? '...' : ''),
      description: `${l.platform} · ${l.grade === 'hot' ? 'Hot' : l.grade === 'warm' ? 'Warm' : 'Cold'}`,
      action: () => {
        navigate(`/leads?keyword=${encodeURIComponent(query)}`)
        onClose()
      },
      category: 'keyword-result' as const,
    }))
  }, [searchEnabled, leadsResult, query, navigate, onClose])

  // [U5] 최근 본 항목을 명령어로 변환
  const recentCommands: CommandItem[] = useMemo(() => {
    const kindIcon: Record<RecentItem['kind'], React.ReactNode> = {
      lead: <Users className="w-5 h-5 text-green-500" />,
      keyword: <Target className="w-5 h-5 text-primary" />,
      viral_target: <MessageSquare className="w-5 h-5 text-orange-500" />,
      competitor: <TrendingUp className="w-5 h-5 text-purple-500" />,
      page: <Clock className="w-5 h-5 text-muted-foreground" />,
    }
    const kindLabel: Record<RecentItem['kind'], string> = {
      lead: '리드',
      keyword: '키워드',
      viral_target: '바이럴 타겟',
      competitor: '경쟁사',
      page: '페이지',
    }
    return recentItems.slice(0, 6).map((item) => {
      const ageMin = Math.max(1, Math.round((Date.now() - item.timestamp) / 60000))
      const ageLabel = ageMin < 60 ? `${ageMin}분 전` : ageMin < 1440 ? `${Math.round(ageMin / 60)}시간 전` : `${Math.round(ageMin / 1440)}일 전`
      return {
        id: `recent-${item.kind}-${item.id}`,
        icon: kindIcon[item.kind],
        label: item.label,
        description: `${kindLabel[item.kind]} · ${ageLabel}`,
        action: () => {
          navigate(item.path)
          onClose()
        },
        category: 'keyword-result' as const,
      }
    })
  }, [recentItems, navigate, onClose])

  // 쿼리에 따른 필터링
  const filteredCommands = useMemo(() => {
    // 검색 결과가 있으면 검색 결과 우선
    if (searchEnabled && (keywordCommands.length > 0 || viralCommands.length > 0 || leadCommands.length > 0)) {
      return [
        ...keywordCommands,
        ...viralCommands,
        ...leadCommands,
      ]
    }

    if (!query.trim()) {
      // [U5] 쿼리 없을 때 최근 항목 먼저, 정적 명령 뒤에
      return [...recentCommands, ...staticCommands]
    }

    const lowerQuery = query.toLowerCase()
    return staticCommands.filter(cmd => {
      const matchLabel = cmd.label.toLowerCase().includes(lowerQuery)
      const matchDesc = cmd.description.toLowerCase().includes(lowerQuery)
      const matchKeywords = cmd.keywords?.some(k => k.toLowerCase().includes(lowerQuery))
      return matchLabel || matchDesc || matchKeywords
    })
  }, [query, staticCommands, searchEnabled, keywordCommands, viralCommands, leadCommands, recentCommands])

  // 키보드 네비게이션
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!isOpen) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (filteredCommands[selectedIndex]) {
          filteredCommands[selectedIndex].action()
        }
        break
      case 'Escape':
        e.preventDefault()
        onClose()
        break
    }
  }, [isOpen, filteredCommands, selectedIndex, onClose])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // 선택 인덱스 리셋
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // 열릴 때 입력 초기화
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
    }
  }, [isOpen])

  if (!isOpen) return null

  return (
    <>
      {/* 배경 오버레이 */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 팔레트 */}
      <div
        className="fixed top-[12%] left-1/2 -translate-x-1/2 w-[calc(100vw-2rem)] max-w-xl z-50 sm:top-[20%]"
        role="dialog"
        aria-modal="true"
        aria-label="명령 팔레트"
      >
        <div className="bg-surface border border-hair-strong rounded-2xl shadow-pop overflow-hidden">
          {/* 검색 입력 */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-hair">
            {isLoading || isSearching ? (
              <Loader2 className="w-[17px] h-[17px] text-faint animate-spin" />
            ) : (
              <Search className="w-[17px] h-[17px] text-faint" strokeWidth={1.8} />
            )}
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="명령 또는 키워드 검색... (3자 이상 입력 시 통합 검색)"
              className="flex-1 bg-transparent outline-none text-strong text-[15px] placeholder:text-faint"
              autoFocus
              aria-label="명령 또는 키워드 검색"
            />
            <kbd className="ros-kbd">ESC</kbd>
          </div>

          {/* 검색 결과 헤더 */}
          {searchEnabled && (keywordCommands.length > 0 || viralCommands.length > 0 || leadCommands.length > 0) && (
            <div className="px-4 py-2 bg-sage-tint border-b border-hair">
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="font-medium text-sage">통합 검색 결과</span>
                {keywordCommands.length > 0 && (
                  <span>키워드 {keywordCommands.length}</span>
                )}
                {viralCommands.length > 0 && (
                  <span>바이럴 {viralCommands.length}</span>
                )}
                {leadCommands.length > 0 && (
                  <span>리드 {leadCommands.length}</span>
                )}
              </div>
            </div>
          )}

          {/* 명령어 목록 */}
          <div className="max-h-80 overflow-y-auto">
            {filteredCommands.length === 0 ? (
              <div className="px-4 py-8 text-center text-muted-foreground">
                {isSearching ? (
                  <p>검색 중...</p>
                ) : (
                  <>
                    <p>"{query}"에 해당하는 결과를 찾을 수 없습니다.</p>
                    <p className="text-sm mt-2">다른 키워드로 검색해 보세요.</p>
                  </>
                )}
              </div>
            ) : (
              <div className="py-2">
                {filteredCommands.map((cmd, idx) => (
                  <button
                    type="button"
                    key={cmd.id}
                    onClick={cmd.action}
                    aria-current={idx === selectedIndex ? 'true' : undefined}
                    className={`
                      w-full flex items-center gap-3 px-4 py-2.5
                      transition-colors text-left
                      ${idx === selectedIndex
                        ? 'bg-sage-tint text-strong'
                        : 'hover:bg-surface-2'
                      }
                    `}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <span className="w-7 h-7 rounded-lg bg-surface-2 grid place-items-center text-sage flex-shrink-0">
                      {cmd.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{cmd.label}</div>
                      <div className="text-sm text-muted-foreground truncate">
                        {cmd.description}
                      </div>
                    </div>
                    {/* 키워드 결과 메타데이터 */}
                    {cmd.category === 'keyword-result' && cmd.metadata && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {cmd.metadata.viral !== undefined && cmd.metadata.viral > 0 && (
                          <span className="flex items-center gap-0.5">
                            <MessageSquare className="w-3 h-3" />
                            {cmd.metadata.viral}
                          </span>
                        )}
                        {cmd.metadata.leads !== undefined && cmd.metadata.leads > 0 && (
                          <span className="flex items-center gap-0.5">
                            <Users className="w-3 h-3" />
                            {cmd.metadata.leads}
                          </span>
                        )}
                      </div>
                    )}
                    {idx === selectedIndex && (
                      <ArrowRight className="w-4 h-4 text-sage" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 푸터 힌트 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-hair bg-surface-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5">
                <kbd className="ros-kbd">↑↓</kbd>
                이동
              </span>
              <span className="flex items-center gap-1.5">
                <kbd className="ros-kbd">Enter</kbd>
                실행
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Command className="w-3 h-3" />
              <span>Marketing Bot v2.0</span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
