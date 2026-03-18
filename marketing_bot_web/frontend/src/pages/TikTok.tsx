import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import PageTransition from '@/components/PageTransition'
import { useUrlState } from '@/hooks/useUrlState'
import TabNavigation from '@/components/ui/TabNavigation'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import { ConfirmModal } from '@/components/ui/Modal'
import {
  Play, TrendingUp, Users, Hash, Music, Plus, Trash2, RefreshCw,
  Eye, Heart, MessageCircle, Share2, ExternalLink, BarChart3
} from 'lucide-react'
import { tiktokApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

export default function TikTok() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'overview' })
  const [newAccount, setNewAccount] = useState('')
  const [accountToDelete, setAccountToDelete] = useState<string | null>(null)

  // API 상태 조회
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['tiktok-status'],
    queryFn: tiktokApi.getStatus,
    staleTime: 60000, // 1분간 캐시
    refetchInterval: 60000,
    retry: 1,
  })

  // 비디오 목록 조회
  const { data: videosData, isLoading: videosLoading } = useQuery({
    queryKey: ['tiktok-videos'],
    queryFn: () => tiktokApi.getVideos({ days: 30, limit: 50 }),
    staleTime: 120000, // 2분간 캐시
    enabled: activeTab === 'videos',
    retry: 1,
  })

  // 트렌드 조회
  const { data: trendsData, isLoading: trendsLoading } = useQuery({
    queryKey: ['tiktok-trends'],
    queryFn: () => tiktokApi.getTrends({ days: 7, limit: 30 }),
    staleTime: 120000, // 2분간 캐시
    enabled: activeTab === 'trends',
    retry: 1,
  })

  // 계정 목록 조회
  const { data: accountsData, isLoading: accountsLoading } = useQuery({
    queryKey: ['tiktok-accounts'],
    queryFn: tiktokApi.getAccounts,
    staleTime: 60000, // 1분간 캐시
    enabled: activeTab === 'accounts',
    retry: 1,
  })

  // 분석 데이터 조회
  const { data: analyticsData, isLoading: analyticsLoading } = useQuery({
    queryKey: ['tiktok-analytics'],
    queryFn: () => tiktokApi.getAnalytics({ days: 30 }),
    staleTime: 300000, // 5분간 캐시 (변동이 적은 분석 데이터)
    enabled: activeTab === 'analytics',
    retry: 1,
  })

  // 스캔 시작
  const scanMutation = useMutation({
    mutationFn: () => tiktokApi.startScan({ scan_trending: true }),
    onSuccess: () => {
      toast.success('틱톡 스캔이 시작되었습니다')
      queryClient.invalidateQueries({ queryKey: ['tiktok-status'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 계정 추가
  const addAccountMutation = useMutation({
    mutationFn: (username: string) => tiktokApi.addAccount({ username, is_competitor: true }),
    onSuccess: () => {
      toast.success('계정이 추가되었습니다')
      setNewAccount('')
      queryClient.invalidateQueries({ queryKey: ['tiktok-accounts'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 계정 삭제
  const deleteAccountMutation = useMutation({
    mutationFn: (username: string) => tiktokApi.deleteAccount(username),
    onSuccess: () => {
      toast.success('계정이 삭제되었습니다')
      setAccountToDelete(null)
      queryClient.invalidateQueries({ queryKey: ['tiktok-accounts'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  const formatNumber = (num: number | null | undefined) => {
    if (!num) return '0'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toLocaleString()
  }

  return (
    <PageTransition>
      <div className="space-y-6">
        {/* 헤더 */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2 flex items-center gap-2">
              <Play className="w-8 h-8 text-pink-500" />
              TikTok
            </h1>
            <p className="text-muted-foreground">
              틱톡 콘텐츠 분석 및 트렌드 모니터링
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={() => scanMutation.mutate()}
              loading={scanMutation.isPending}
              icon={<RefreshCw className="w-4 h-4" />}
              className="bg-pink-500 hover:bg-pink-600"
            >
              스캔 시작
            </Button>
          </div>
        </div>

        {/* 상태 카드 */}
        {!statusLoading && status && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 text-muted-foreground mb-2">
                <Play className="w-4 h-4" />
                <span className="text-sm">총 비디오</span>
              </div>
              <div className="text-2xl font-bold">{formatNumber(status.videos?.total_videos)}</div>
            </div>
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 text-muted-foreground mb-2">
                <Users className="w-4 h-4" />
                <span className="text-sm">모니터링 계정</span>
              </div>
              <div className="text-2xl font-bold">{status.videos?.unique_accounts || 0}</div>
            </div>
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 text-muted-foreground mb-2">
                <TrendingUp className="w-4 h-4" />
                <span className="text-sm">상승 트렌드</span>
              </div>
              <div className="text-2xl font-bold text-green-500">{status.trends?.rising_trends || 0}</div>
            </div>
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 text-muted-foreground mb-2">
                <BarChart3 className="w-4 h-4" />
                <span className="text-sm">상태</span>
              </div>
              <div className={`text-lg font-bold ${status.status === 'active' ? 'text-green-500' : 'text-yellow-500'}`}>
                {status.status === 'active' ? '활성' : '대기중'}
              </div>
            </div>
          </div>
        )}

        {/* 탭 네비게이션 */}
        <TabNavigation
          tabs={[
            { id: 'overview', label: '개요' },
            { id: 'videos', label: '비디오' },
            { id: 'trends', label: '트렌드' },
            { id: 'accounts', label: '계정 관리' },
            { id: 'analytics', label: '분석' },
          ]}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          ariaLabel="TikTok 탭"
        />

        {/* 개요 탭 */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* 최근 활동 요약 */}
            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">최근 활동</h3>
              {!statusLoading && status ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <span>마지막 스캔</span>
                    <span className="text-muted-foreground">
                      {status.last_scan ? new Date(status.last_scan).toLocaleString('ko-KR') : '기록 없음'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <span>경쟁사 비디오</span>
                    <span className="font-medium">{status.videos?.competitor_videos || 0}개</span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <span>추적 중인 트렌드</span>
                    <span className="font-medium">{status.trends?.total_trends || 0}개</span>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  로딩 중...
                </div>
              )}
            </div>

            {/* 시작 가이드 */}
            {status && status.videos?.total_videos === 0 && (
              <div className="bg-pink-500/10 border border-pink-500/30 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-pink-500 mb-2">시작하기</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  틱톡 분석을 시작하려면 먼저 모니터링할 계정을 추가하세요.
                </p>
                <ol className="text-sm space-y-2 text-muted-foreground">
                  <li>1. "계정 관리" 탭에서 경쟁사 틱톡 계정 추가</li>
                  <li>2. "스캔 시작" 버튼으로 데이터 수집</li>
                  <li>3. "비디오" 및 "트렌드" 탭에서 분석 결과 확인</li>
                </ol>
              </div>
            )}
          </div>
        )}

        {/* 비디오 탭 */}
        {activeTab === 'videos' && (
          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h3 className="font-semibold">틱톡 비디오</h3>
              <span className="text-sm text-muted-foreground">
                총 {videosData?.stats?.total || 0}개
              </span>
            </div>

            {videosLoading ? (
              <div className="p-8 text-center text-muted-foreground">로딩 중...</div>
            ) : videosData?.videos?.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                <Play className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>수집된 비디오가 없습니다</p>
                <p className="text-sm mt-2">스캔을 시작하여 데이터를 수집하세요</p>
                <Button
                  variant="primary"
                  className="mt-4 bg-pink-500 hover:bg-pink-600"
                  onClick={() => scanMutation.mutate()}
                  loading={scanMutation.isPending}
                  icon={<RefreshCw className="w-4 h-4" />}
                >
                  스캔 시작
                </Button>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {videosData?.videos?.map((video: any) => (
                  <div key={video.video_id} className="p-4 hover:bg-muted/50 transition-colors">
                    <div className="flex gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium">@{video.author_username}</span>
                          {video.is_competitor && (
                            <span className="px-2 py-0.5 bg-pink-500/10 text-pink-500 text-xs rounded">
                              경쟁사
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
                          {video.description || '설명 없음'}
                        </p>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Eye className="w-4 h-4" />
                            {formatNumber(video.view_count)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Heart className="w-4 h-4" />
                            {formatNumber(video.like_count)}
                          </span>
                          <span className="flex items-center gap-1">
                            <MessageCircle className="w-4 h-4" />
                            {formatNumber(video.comment_count)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Share2 className="w-4 h-4" />
                            {formatNumber(video.share_count)}
                          </span>
                          <span className={`font-medium ${
                            video.engagement_rate > 5 ? 'text-green-500' :
                            video.engagement_rate > 2 ? 'text-yellow-500' : 'text-muted-foreground'
                          }`}>
                            {video.engagement_rate?.toFixed(1)}% 참여율
                          </span>
                        </div>
                        {video.hashtags?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {video.hashtags.slice(0, 5).map((tag: string, i: number) => (
                              <span key={i} className="px-2 py-0.5 bg-muted text-xs rounded">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {video.video_url && (
                        <a
                          href={video.video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 hover:bg-muted rounded-lg transition-colors"
                        >
                          <ExternalLink className="w-5 h-5 text-muted-foreground" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 트렌드 탭 */}
        {activeTab === 'trends' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 해시태그 트렌드 */}
            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-border flex items-center gap-2">
                <Hash className="w-5 h-5 text-pink-500" />
                <h3 className="font-semibold">해시태그 트렌드</h3>
              </div>

              {trendsLoading ? (
                <div className="p-8 text-center text-muted-foreground">로딩 중...</div>
              ) : (
                <div className="divide-y divide-border">
                  {trendsData?.trends
                    ?.filter((t: any) => t.trend_type === 'hashtag')
                    ?.slice(0, 10)
                    ?.map((trend: any, index: number) => (
                      <div key={trend.trend_key} className="p-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm text-muted-foreground w-6">{index + 1}</span>
                          <div>
                            <div className="font-medium">#{trend.trend_key}</div>
                            <div className="text-xs text-muted-foreground">
                              {trend.video_count}개 비디오
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {trend.is_rising && (
                            <TrendingUp className="w-4 h-4 text-green-500" />
                          )}
                          <span className="text-sm font-medium">
                            {trend.trend_score?.toFixed(1)}
                          </span>
                        </div>
                      </div>
                    ))}
                  {(!trendsData?.trends || trendsData.trends.filter((t: any) => t.trend_type === 'hashtag').length === 0) && (
                    <div className="p-8 text-center text-muted-foreground">
                      트렌드 데이터가 없습니다
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 음악 트렌드 */}
            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-border flex items-center gap-2">
                <Music className="w-5 h-5 text-pink-500" />
                <h3 className="font-semibold">음악 트렌드</h3>
              </div>

              {trendsLoading ? (
                <div className="p-8 text-center text-muted-foreground">로딩 중...</div>
              ) : (
                <div className="divide-y divide-border">
                  {trendsData?.trends
                    ?.filter((t: any) => t.trend_type === 'music')
                    ?.slice(0, 10)
                    ?.map((trend: any, index: number) => (
                      <div key={trend.trend_key} className="p-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm text-muted-foreground w-6">{index + 1}</span>
                          <div>
                            <div className="font-medium">{trend.trend_name || trend.trend_key}</div>
                            <div className="text-xs text-muted-foreground">
                              {trend.video_count}개 비디오
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {trend.is_rising && (
                            <TrendingUp className="w-4 h-4 text-green-500" />
                          )}
                          <span className="text-sm font-medium">
                            {trend.trend_score?.toFixed(1)}
                          </span>
                        </div>
                      </div>
                    ))}
                  {(!trendsData?.trends || trendsData.trends.filter((t: any) => t.trend_type === 'music').length === 0) && (
                    <div className="p-8 text-center text-muted-foreground">
                      음악 트렌드 데이터가 없습니다
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 계정 관리 탭 */}
        {activeTab === 'accounts' && (
          <>
            <ConfirmModal
              isOpen={accountToDelete !== null}
              onClose={() => setAccountToDelete(null)}
              onConfirm={() => accountToDelete && deleteAccountMutation.mutate(accountToDelete)}
              title="계정 삭제"
              message={`@${accountToDelete} 계정을 삭제하시겠습니까?`}
              confirmText="삭제"
              cancelText="취소"
              variant="danger"
              loading={deleteAccountMutation.isPending}
            />

            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">모니터링 계정</h3>

              {/* 계정 추가 폼 */}
              <div className="flex gap-2 mb-6">
                <input
                  type="text"
                  value={newAccount}
                  onChange={(e) => setNewAccount(e.target.value)}
                  placeholder="틱톡 사용자명 입력..."
                  className="flex-1 px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newAccount.trim()) {
                      addAccountMutation.mutate(newAccount.trim())
                    }
                  }}
                />
                <Button
                  variant="primary"
                  onClick={() => newAccount.trim() && addAccountMutation.mutate(newAccount.trim())}
                  disabled={!newAccount.trim()}
                  loading={addAccountMutation.isPending}
                  icon={<Plus className="w-4 h-4" />}
                  className="bg-pink-500 hover:bg-pink-600"
                >
                  추가
                </Button>
              </div>

              {/* 계정 목록 */}
              {accountsLoading ? (
                <div className="text-center py-8 text-muted-foreground">로딩 중...</div>
              ) : accountsData?.accounts?.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>등록된 계정이 없습니다</p>
                  <p className="text-sm mt-2">위 입력창에서 모니터링할 틱톡 계정을 추가하세요</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {accountsData?.accounts?.map((account: any) => (
                    <div
                      key={account.username}
                      className="flex items-center justify-between p-3 bg-muted/50 rounded-lg group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-pink-500/10 rounded-full flex items-center justify-center">
                          <Users className="w-5 h-5 text-pink-500" />
                        </div>
                        <div>
                          <div className="font-medium">@{account.username}</div>
                          <div className="text-xs text-muted-foreground">
                            {account.category || '경쟁사'} |
                            추가일: {new Date(account.added_at).toLocaleDateString('ko-KR')}
                          </div>
                        </div>
                      </div>
                      <IconButton
                        icon={<Trash2 className="w-4 h-4" />}
                        onClick={() => setAccountToDelete(account.username)}
                        size="sm"
                        title="삭제"
                        className="opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-red-500"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* 분석 탭 */}
        {activeTab === 'analytics' && (
          <div className="space-y-6">
            {analyticsLoading ? (
              <div className="text-center py-12 text-muted-foreground">분석 데이터 로딩 중...</div>
            ) : analyticsData ? (
              <>
                {/* 전체 통계 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-card border border-border rounded-lg p-4">
                    <div className="text-sm text-muted-foreground mb-1">총 조회수</div>
                    <div className="text-2xl font-bold">{formatNumber(analyticsData.overall?.total_views)}</div>
                  </div>
                  <div className="bg-card border border-border rounded-lg p-4">
                    <div className="text-sm text-muted-foreground mb-1">총 좋아요</div>
                    <div className="text-2xl font-bold">{formatNumber(analyticsData.overall?.total_likes)}</div>
                  </div>
                  <div className="bg-card border border-border rounded-lg p-4">
                    <div className="text-sm text-muted-foreground mb-1">평균 참여율</div>
                    <div className="text-2xl font-bold">
                      {analyticsData.overall?.avg_engagement?.toFixed(1) || 0}%
                    </div>
                  </div>
                  <div className="bg-card border border-border rounded-lg p-4">
                    <div className="text-sm text-muted-foreground mb-1">최고 참여율</div>
                    <div className="text-2xl font-bold text-green-500">
                      {analyticsData.overall?.top_engagement?.toFixed(1) || 0}%
                    </div>
                  </div>
                </div>

                {/* Top 계정 */}
                <div className="bg-card border border-border rounded-lg p-6">
                  <h3 className="text-lg font-semibold mb-4">Top 계정</h3>
                  {(analyticsData.top_accounts?.length ?? 0) > 0 ? (
                    <div className="space-y-3">
                      {analyticsData.top_accounts?.map((account: any, index: number) => (
                        <div key={account.author_username} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                          <div className="flex items-center gap-3">
                            <span className="text-lg font-bold text-muted-foreground w-6">{index + 1}</span>
                            <div>
                              <div className="font-medium">@{account.author_username}</div>
                              <div className="text-xs text-muted-foreground">
                                {account.video_count}개 비디오
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-bold">{formatNumber(account.total_views)}</div>
                            <div className="text-xs text-muted-foreground">조회수</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      분석할 데이터가 없습니다
                    </div>
                  )}
                </div>

                {/* Top 해시태그 */}
                <div className="bg-card border border-border rounded-lg p-6">
                  <h3 className="text-lg font-semibold mb-4">인기 해시태그</h3>
                  {(analyticsData.top_hashtags?.length ?? 0) > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {analyticsData.top_hashtags?.map((tag: any) => (
                        <span
                          key={tag.hashtag}
                          className="px-3 py-1.5 bg-pink-500/10 text-pink-500 rounded-full text-sm"
                        >
                          #{tag.hashtag} ({tag.video_count})
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      해시태그 데이터가 없습니다
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                분석 데이터를 불러올 수 없습니다
              </div>
            )}
          </div>
        )}
      </div>
    </PageTransition>
  )
}
