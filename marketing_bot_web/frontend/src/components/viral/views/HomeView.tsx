import { UseMutationResult } from '@tanstack/react-query'
import Button from '@/components/ui/Button'
import MissionProgress from '@/components/ui/MissionProgress'
import TodaysQueue from '@/components/viral/TodaysQueue'
import { ScanBatch } from '@/components/viral/FilterBar'
import { CategoryStatResult } from '@/types/viral'
import { HomeStats } from '@/services/api/viral'

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
  stats?: ViralStats
  homeStats?: HomeStats
  qualitySummary?: {
    feedback_total: number
    acceptance_rate: number | null
    edit_rate: number | null
    feedback_by_rating: Record<string, number>
  } | null
  opsStatus?: {
    audit_events: number
    feedback_events: number
    api_auth_enabled: boolean
    backup: {
      total_backups?: number
      days_since_backup?: number | null
      db_size_mb?: number
      error?: string
    }
  } | null
  scanBatches?: ScanBatch[]
  platformStats: Record<string, PlatformStat>
  categoryStats: CategoryStatResult[]

  scanningModule: string | null
  isScanning: boolean
  showScanSettings: boolean
  scanSettings: ScanSettings
  homeScanBatch: string

  isVerifying: boolean
  verifyLimit: number
  verifyResults: {
    total: number
    commentable: number
    not_commentable: number
  } | null

  onMissionComplete: () => void
  onMissionStop: () => void
  onSelectCategory: (category: string) => void
  onBatchVerify: (category: string | undefined, limit: number) => void
  onViewList: () => void
  onKpiNavigate?: (target: 'pending' | 'today_processed' | 'week_processed' | 'hot_pending') => void
  onToggleScanSettings: () => void
  onScanSettingsChange: (settings: ScanSettings) => void
  onVerifyLimitChange: (limit: number) => void
  onHomeScanBatchChange: (batch: string) => void
  runScanMutation: UseMutationResult<any, Error, void, unknown>
  stopScan: () => Promise<void>
}

const allPlatforms = ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok']

const platformLabels: Record<string, string> = {
  cafe: '카페',
  blog: '블로그',
  kin: '지식iN',
  place: '플레이스',
  karrot: '당근',
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
}

function formatCount(value?: number) {
  return (value || 0).toLocaleString('ko-KR')
}

export function HomeView({
  stats,
  homeStats,
  qualitySummary,
  opsStatus,
  scanBatches,
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
  onToggleScanSettings,
  onScanSettingsChange,
  onVerifyLimitChange,
  onHomeScanBatchChange,
  runScanMutation,
  stopScan,
}: HomeViewProps) {
  const workTotal = homeStats?.total_count ?? 0
  const processedTotal = (stats?.posted || 0) + (stats?.skipped || 0)

  return (
    <div className="space-y-6">
      <section className="border-b border-border pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-normal">바이럴 댓글 작업</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              최신 Legion 스캔에서 나온 핵심 진료 카테고리만 기본 작업 큐로 보여줍니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onViewList} variant="primary" size="lg">
              전체 작업 목록
            </Button>
            {isScanning ? (
              <Button onClick={stopScan} variant="danger" size="lg">
                스캔 중지
              </Button>
            ) : (
              <Button onClick={() => runScanMutation.mutate()} variant="outline" size="lg">
                새 스캔 실행
              </Button>
            )}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">현재 작업 큐</div>
          <div className="mt-1 text-2xl font-bold">{formatCount(workTotal)}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">전체 대기</div>
          <div className="mt-1 text-2xl font-bold">{formatCount(stats?.pending)}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">처리 완료</div>
          <div className="mt-1 text-2xl font-bold">{formatCount(processedTotal)}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">댓글 가능 검증</div>
          <div className="mt-1 text-2xl font-bold">
            {verifyResults ? `${verifyResults.commentable}/${verifyResults.total}` : '-'}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">댓글 품질 피드백</div>
          <div className="mt-1 text-2xl font-bold">
            {qualitySummary?.feedback_total ?? 0}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            좋음 {qualitySummary?.feedback_by_rating?.good ?? 0} / 수정필요 {qualitySummary?.feedback_by_rating?.needs_edit ?? 0}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">초안 수용률</div>
          <div className="mt-1 text-2xl font-bold">
            {qualitySummary?.acceptance_rate != null ? `${qualitySummary.acceptance_rate}%` : '-'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            최근 14일 직원 피드백 기준
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs text-muted-foreground">운영 기록 / 백업</div>
          <div className="mt-1 text-2xl font-bold">
            {opsStatus?.audit_events ?? 0}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            마지막 백업 {opsStatus?.backup?.days_since_backup ?? '-'}일 전
          </div>
        </div>
      </section>

      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName="바이럴 타겟 스캔"
          onComplete={onMissionComplete}
          onStop={onMissionStop}
        />
      )}

      <TodaysQueue onOpenCategory={(category) => onSelectCategory(category)} />

      <section className="rounded-lg border border-border bg-card p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-xl font-bold">카테고리별 작업</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              직원은 아래 카테고리에서 바로 댓글 작업을 시작하면 됩니다.
            </p>
          </div>
          {scanBatches && scanBatches.length > 0 && (
            <select
              value={homeScanBatch}
              onChange={(event) => onHomeScanBatchChange(event.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">최신 작업 큐</option>
              {scanBatches.slice(0, 12).map((batch) => (
                <option key={batch.batch_id} value={batch.batch_id}>
                  {batch.batch_label}
                </option>
              ))}
            </select>
          )}
        </div>

        {categoryStats.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center">
            <div className="text-lg font-semibold">작업할 타겟이 없습니다</div>
            <p className="mt-2 text-sm text-muted-foreground">
              새 스캔을 실행하면 최신 Legion 기반 작업 큐가 다시 채워집니다.
            </p>
            <Button
              onClick={() => runScanMutation.mutate()}
              disabled={isScanning}
              variant="primary"
              size="lg"
              className="mt-4"
            >
              새 스캔 실행
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {categoryStats.map(({ category, count, avgScore }) => (
              <div key={category} className="rounded-lg border border-border bg-background p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold">{category}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      평균 우선순위 {avgScore.toFixed(1)}점
                    </p>
                  </div>
                  <div className="text-2xl font-bold text-primary">{formatCount(count)}</div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Button
                    onClick={() => onSelectCategory(category)}
                    size="sm"
                    variant="primary"
                  >
                    작업 시작
                  </Button>
                  <Button
                    onClick={() => onBatchVerify(category, 0)}
                    disabled={isVerifying}
                    size="sm"
                    variant="outline"
                  >
                    검증
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-bold">스캔 설정</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              기본값 그대로 실행하면 최신 Legion 키워드 기반으로 새 타겟을 수집합니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onToggleScanSettings} variant="outline" size="sm">
              {showScanSettings ? '설정 닫기' : '설정 열기'}
            </Button>
            <Button
              onClick={() => onBatchVerify(undefined, verifyLimit)}
              loading={isVerifying}
              variant="secondary"
              size="sm"
            >
              일괄 검증
            </Button>
          </div>
        </div>

        {showScanSettings && (
          <div className="mt-5 space-y-5 border-t border-border pt-5">
            <div>
              <div className="mb-2 text-sm font-medium">수집 플랫폼</div>
              <div className="flex flex-wrap gap-2">
                {allPlatforms.map((platform) => {
                  const selected = scanSettings.platforms.includes(platform)
                  return (
                    <button
                      key={platform}
                      onClick={() => {
                        const platforms = selected
                          ? scanSettings.platforms.filter((item) => item !== platform)
                          : [...scanSettings.platforms, platform]
                        onScanSettingsChange({ ...scanSettings, platforms })
                      }}
                      className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                        selected
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-background hover:bg-muted'
                      }`}
                    >
                      {platformLabels[platform] || platform}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
              <label className="block">
                <span className="mb-2 block text-sm font-medium">
                  최대 결과 수: {scanSettings.maxResults.toLocaleString('ko-KR')}
                </span>
                <input
                  type="range"
                  min="100"
                  max="1000"
                  step="100"
                  value={scanSettings.maxResults}
                  onChange={(event) =>
                    onScanSettingsChange({
                      ...scanSettings,
                      maxResults: parseInt(event.target.value, 10),
                    })
                  }
                  className="w-full"
                />
              </label>
              <select
                value={verifyLimit}
                onChange={(event) => onVerifyLimitChange(Number(event.target.value))}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
              >
                <option value={20}>20개 검증</option>
                <option value={50}>50개 검증</option>
                <option value={100}>100개 검증</option>
                <option value={200}>200개 검증</option>
                <option value={0}>전체 검증</option>
              </select>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
