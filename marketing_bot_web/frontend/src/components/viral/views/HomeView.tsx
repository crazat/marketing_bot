/**
 * Viral Hunter - 홈 화면
 * 전체 현황, 플랫폼별 통계, 카테고리 카드, 스캔 실행
 */

import { UseMutationResult } from '@tanstack/react-query'
import Button from '@/components/ui/Button'
import MissionProgress from '@/components/ui/MissionProgress'
import { PerformanceDashboard } from '@/components/viral/PerformanceDashboard'
import { CommentPerformance } from '@/components/viral/CommentPerformance'
import { TrendInsights } from '@/components/viral/TrendInsights'
import { ViralCharts } from '@/components/viral/ViralCharts'
import TodaysQueue from '@/components/viral/TodaysQueue'
import KpiWidget from '@/components/viral/KpiWidget'
import { ScanBatch } from '@/components/viral/FilterBar'
import { CategoryStatResult } from '@/types/viral'
import { HomeStats } from '@/services/api/viral'
import { TerminalGuide } from '@/components/ui/TerminalGuide'
import { getPageCommands } from '@/utils/terminalCommands'

interface ViralStats {
  total_targets: number
  pending: number
  posted: number
  skipped: number
}

interface PlatformStat {
  count: number
  avgScore: number
  maxScore: number
}

interface ScanSettings {
  platforms: string[]
  maxResults: number
}

interface HomeViewProps {
  // 데이터
  stats?: ViralStats
  homeStats?: HomeStats  // [Phase 9.0] 백엔드 집계 통계
  scanBatches?: ScanBatch[]
  platformStats: Record<string, PlatformStat>
  categoryStats: CategoryStatResult[]

  // 스캔 상태
  scanningModule: string | null
  isScanning: boolean
  showScanSettings: boolean
  scanSettings: ScanSettings
  homeScanBatch: string

  // 검증 상태
  isVerifying: boolean
  verifyLimit: number
  verifyResults: {
    total: number
    commentable: number
    not_commentable: number
  } | null

  // 핸들러
  onMissionComplete: () => void
  onMissionStop: () => void
  onSelectCategory: (category: string) => void
  onBatchVerify: (category: string | undefined, limit: number) => void
  onViewList: () => void
  // [V2] KPI 카드 클릭 → 필터링된 ListView 이동
  onKpiNavigate?: (target: 'pending' | 'today_processed' | 'week_processed' | 'hot_pending') => void
  onToggleScanSettings: () => void
  onScanSettingsChange: (settings: ScanSettings) => void
  onVerifyLimitChange: (limit: number) => void
  onHomeScanBatchChange: (batch: string) => void
  runScanMutation: UseMutationResult<any, Error, void, unknown>
  stopScan: () => Promise<void>
}

const platformIcons: Record<string, { icon: string; label: string }> = {
  cafe: { icon: '☕', label: '네이버 카페' },
  blog: { icon: '📝', label: '블로그' },
  kin: { icon: '❓', label: '지식iN' },
  youtube: { icon: '📺', label: '유튜브' },
  instagram: { icon: '📸', label: '인스타그램' },
  tiktok: { icon: '🎵', label: '틱톡' },
  place: { icon: '📍', label: '플레이스' },
  karrot: { icon: '🥕', label: '당근' },
  other: { icon: '📌', label: '기타' },
}

const allPlatforms = ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok']

export function HomeView({
  stats,
  homeStats,
  scanBatches,
  platformStats,
  categoryStats,
  scanningModule,
  isScanning,
  showScanSettings,
  scanSettings,
  homeScanBatch,
  isVerifying,
  verifyLimit,
  verifyResults,
  onMissionComplete,
  onMissionStop,
  onSelectCategory,
  onBatchVerify,
  onViewList,
  onKpiNavigate,
  onToggleScanSettings,
  onScanSettingsChange,
  onVerifyLimitChange,
  onHomeScanBatchChange,
  runScanMutation,
  stopScan,
}: HomeViewProps) {
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="text-center py-8 border-b border-border">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-yellow-500 to-red-500 bg-clip-text text-transparent mb-2">
          🔥 바이럴 헌터 워크스테이션
        </h1>
        <p className="text-muted-foreground">카테고리별 우선순위 작업 시스템</p>
        <div className="mt-4">
          <Button onClick={onViewList} variant="outline" title="여러 카테고리를 가로질러 필터링하고 일괄 승인/스킵/삭제하는 모드">
            📋 일괄 작업 모드 (전체 관리)
          </Button>
        </div>
      </div>

      {/* [U6/V2] KPI 위젯 — 카드 클릭으로 ListView 진입 */}
      <KpiWidget onNavigate={onKpiNavigate} />

      {/* [U1] 오늘의 작업 큐 — 최우선 노출 */}
      <TodaysQueue
        onOpenCategory={(cat) => onSelectCategory(cat)}
      />


      {/* 실시간 스캔 진행 상황 */}
      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName="바이럴 타겟 스캔"
          onComplete={onMissionComplete}
          onStop={onMissionStop}
        />
      )}

      {/* 전체 현황 */}
      <div>
        <h2 className="text-2xl font-bold mb-4">📊 전체 현황</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-yellow-500">{stats?.total_targets || 0}</div>
            <div className="text-sm text-muted-foreground mt-2">총 타겟</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-yellow-500">{stats?.pending || 0}</div>
            <div className="text-sm text-muted-foreground mt-2">⏳ 대기중</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-green-500">{stats?.posted || 0}</div>
            <div className="text-sm text-muted-foreground mt-2">✅ 완료</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-blue-500">{stats?.skipped || 0}</div>
            <div className="text-sm text-muted-foreground mt-2">⏭️ 건너뜀</div>
          </div>
        </div>
      </div>

      {/* 플랫폼별 통계 */}
      {Object.keys(platformStats).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">📊 플랫폼별 현황</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(platformStats).map(([platform, platformData]) => {
              const info = platformIcons[platform] || platformIcons.other
              const statData = platformData as PlatformStat
              return (
                <div
                  key={platform}
                  className="bg-card border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{info.icon}</span>
                    <span className="font-medium text-sm">{info.label}</span>
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <div className="flex justify-between">
                      <span>타겟 수:</span>
                      <span className="font-semibold text-foreground">{statData.count}개</span>
                    </div>
                    <div className="flex justify-between">
                      <span>평균 점수:</span>
                      <span className="font-semibold text-foreground">{statData.avgScore.toFixed(1)}점</span>
                    </div>
                    <div className="flex justify-between">
                      <span>최고 점수:</span>
                      <span className="font-semibold text-foreground">{statData.maxScore.toFixed(0)}점</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Decision Intelligence 컴포넌트들 */}
      <PerformanceDashboard compact={true} />
      <CommentPerformance days={30} compact={true} />
      <TrendInsights compact={false} />

      {/* [Phase 9.0] 데이터 시각화 - 백엔드 집계 통계 사용 */}
      {homeStats && (
        <ViralCharts statsData={homeStats} compact={true} />
      )}

      {/* 스캔 실행 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold mb-1">🔍 바이럴 타겟 스캔</h3>
            <p className="text-sm text-muted-foreground">
              네이버 블로그, 카페, 지식iN에서 새로운 타겟을 발굴합니다
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={onToggleScanSettings} variant="secondary" size="sm">
              ⚙️ 설정 {showScanSettings ? '접기' : '펼치기'}
            </Button>
            {isScanning ? (
              <Button onClick={stopScan} variant="danger" size="lg">
                ⏹️ 스캔 중지
              </Button>
            ) : (
              <Button
                onClick={() => runScanMutation.mutate()}
                size="lg"
                className="bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600"
              >
                🔍 스캔 실행
              </Button>
            )}
          </div>
        </div>

        {/* 스캔 설정 패널 */}
        {showScanSettings && (
          <div className="mt-4 pt-4 border-t border-border space-y-4">
            {/* 플랫폼 선택 */}
            <div>
              <label className="block text-sm font-medium mb-2">플랫폼 선택</label>
              <div className="flex flex-wrap gap-2">
                {allPlatforms.map((platform) => {
                  const info = platformIcons[platform] || platformIcons.other
                  const isSelected = scanSettings.platforms.includes(platform)
                  return (
                    <button
                      key={platform}
                      onClick={() => {
                        const newPlatforms = isSelected
                          ? scanSettings.platforms.filter((p) => p !== platform)
                          : [...scanSettings.platforms, platform]
                        onScanSettingsChange({ ...scanSettings, platforms: newPlatforms })
                      }}
                      className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                        isSelected
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground hover:bg-accent'
                      }`}
                    >
                      {info.icon} {info.label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 최대 결과 수 */}
            <div>
              <label className="block text-sm font-medium mb-2">
                최대 결과 수: {scanSettings.maxResults}개
              </label>
              <input
                type="range"
                min="100"
                max="1000"
                step="100"
                value={scanSettings.maxResults}
                onChange={(e) =>
                  onScanSettingsChange({
                    ...scanSettings,
                    maxResults: parseInt(e.target.value),
                  })
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>100</span>
                <span>500</span>
                <span>1000</span>
              </div>
            </div>
          </div>
        )}

        {/* 터미널 실행 가이드 */}
        <div className="mt-4">
          <TerminalGuide commands={getPageCommands('viral')} />
        </div>
      </div>

      {/* 일괄 검증 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold mb-1">🔍 타겟 일괄 검증</h3>
            <p className="text-sm text-muted-foreground">
              댓글 작성 가능 여부를 일괄 확인합니다
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={verifyLimit}
              onChange={(e) => onVerifyLimitChange(Number(e.target.value))}
              className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={isVerifying}
            >
              <option value={20}>20개</option>
              <option value={50}>50개</option>
              <option value={100}>100개</option>
              <option value={200}>200개</option>
              <option value={0}>전체</option>
            </select>
            <Button
              onClick={() => onBatchVerify(undefined, verifyLimit)}
              loading={isVerifying}
              size="lg"
              className="bg-blue-500 hover:bg-blue-600"
            >
              🔍 검증 시작 {verifyLimit === 0 ? '(전체)' : `(${verifyLimit}개)`}
            </Button>
          </div>
        </div>
        {verifyResults && (
          <div className="mt-4 p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold">{verifyResults.total}</div>
                <div className="text-xs text-muted-foreground">검증됨</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-500">{verifyResults.commentable}</div>
                <div className="text-xs text-muted-foreground">댓글 가능</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-500">{verifyResults.not_commentable}</div>
                <div className="text-xs text-muted-foreground">댓글 불가</div>
              </div>
              <div className="flex-1 text-right">
                <div className="text-sm text-muted-foreground">
                  성공률:{' '}
                  <span className="font-bold text-green-500">
                    {verifyResults.total > 0
                      ? ((verifyResults.commentable / verifyResults.total) * 100).toFixed(1)
                      : 0}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 카테고리 카드 */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">🎯 카테고리별 작업</h2>
          {scanBatches && scanBatches.length > 0 && (
            <select
              value={homeScanBatch}
              onChange={(e) => onHomeScanBatchChange(e.target.value)}
              className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
            >
              <option value="">전체 스캔</option>
              {scanBatches.map((batch) => (
                <option key={batch.batch_id} value={batch.batch_id}>
                  {batch.batch_label}
                </option>
              ))}
            </select>
          )}
        </div>

        {categoryStats.length === 0 ? (
          <section
            aria-label="대기 타겟 없음"
            className="relative bg-card border border-border p-10 md:p-12 overflow-hidden"
          >
            <span
              aria-hidden
              className="absolute right-6 top-2 text-[10rem] md:text-[12rem] leading-none font-display text-foreground/[0.03] select-none pointer-events-none"
            >
              空
            </span>
            <div className="relative max-w-xl">
              <div className="caps text-muted-foreground mb-4">Empty Queue · 대기 없음</div>
              <h3 className="font-display text-2xl md:text-3xl leading-tight mb-3">
                오늘 처리할 타겟이 없습니다
              </h3>
              <p className="text-sm md:text-base text-muted-foreground leading-relaxed mb-6">
                좋은 상태예요. 새로운 바이럴 스캔을 실행해 잠재 고객이 있는
                블로그·카페·지식인 글을 발굴해 보세요. 스캔은 보통 1–2시간이 걸립니다.
              </p>
              <ol className="text-sm text-muted-foreground space-y-2 mb-7 border-l border-border pl-4">
                <li><span className="font-display text-primary mr-2">01</span>스캔 실행 → 바이럴 타겟 수집</li>
                <li><span className="font-display text-primary mr-2">02</span>AI 댓글 생성 → 승인/스킵</li>
                <li><span className="font-display text-primary mr-2">03</span>네이버·카페 현장에 댓글 게시</li>
              </ol>
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => runScanMutation.mutate()}
                  disabled={isScanning}
                  variant="primary"
                  size="lg"
                >
                  🚀 지금 스캔 실행
                </Button>
                <Button onClick={onViewList} variant="ghost" size="lg" title="필터·일괄 처리 모드">
                  📋 일괄 작업 모드
                </Button>
              </div>
            </div>
          </section>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {categoryStats.map(({ category, count, avgScore, maxScore, priority }) => (
              <div
                key={category}
                className="bg-card border border-border rounded-lg p-6 hover:border-primary/50 transition-all group"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold">{category}</h3>
                  <span className="text-3xl font-bold text-yellow-500">{count}</span>
                </div>

                <div className="space-y-2 text-sm text-muted-foreground mb-4">
                  <div className="flex justify-between">
                    <span>평균 우선순위:</span>
                    <span className="font-semibold text-foreground">{avgScore.toFixed(1)}점</span>
                  </div>
                  <div className="flex justify-between">
                    <span>최고 우선순위:</span>
                    <span className="font-semibold text-foreground">{maxScore.toFixed(0)}점</span>
                  </div>
                  <div className="flex justify-between">
                    <span>작업 우선도:</span>
                    <span className="font-semibold text-foreground">{priority.toFixed(0)}</span>
                  </div>
                </div>

                {/* 우선순위 바 */}
                <div className="w-full bg-muted rounded-full h-2 mb-4">
                  <div
                    className="bg-gradient-to-r from-yellow-500 to-red-500 h-2 rounded-full"
                    style={{ width: `${Math.min((maxScore / 150) * 100, 100)}%` }}
                  />
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={(e) => {
                      e.stopPropagation()
                      onBatchVerify(category, 0)
                    }}
                    disabled={isVerifying}
                    size="lg"
                    className="bg-blue-500 hover:bg-blue-600"
                    title={`이 카테고리의 모든 타겟 (${count}개) 검증`}
                  >
                    {isVerifying ? '⏳' : '🔍'} 전체 검증 ({count}개)
                  </Button>
                  <Button
                    onClick={(e) => {
                      e.stopPropagation()
                      onSelectCategory(category)
                    }}
                    size="lg"
                  >
                    → 작업 시작
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
