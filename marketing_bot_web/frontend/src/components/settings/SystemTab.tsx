/**
 * 시스템 정보 탭 컴포넌트
 * 시스템 상태, 진단 정보, DB 마이그레이션 관리
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { hudApi, backupApi, migrationApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import {
  HardDrive,
  Database,
  FileCode,
  RefreshCw,
  Play,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'

interface MigrationItem {
  version: string
  description: string
  applied_at?: string
}

interface MigrationStatus {
  total_migrations: number
  applied_count: number
  pending_count: number
  current_version: string | null
  pending: MigrationItem[]
  applied: MigrationItem[]
}

interface SystemStatus {
  scheduler_status?: string
  last_pathfinder_run?: string
  last_rank_check?: string
}

interface BackupStatus {
  db_size_mb?: number
  total_backups?: number
  warning_level?: 'critical' | 'warning' | 'ok'
}

export default function SystemTab() {
  const queryClient = useQueryClient()
  const toast = useToast()

  // 시스템 상태 조회
  const { data: systemStatus, isLoading } = useQuery<SystemStatus | null>({
    queryKey: ['system-status'],
    queryFn: () => hudApi.getSystemStatus().catch(() => null),
    refetchInterval: 30000,
    retry: 1,
  })

  // 백업 상태 조회
  const { data: backupStatus } = useQuery<BackupStatus | null>({
    queryKey: ['backup-status'],
    queryFn: () => backupApi.getStatus().catch(() => null),
    refetchInterval: 60000,
    retry: 1,
  })

  // 마이그레이션 상태 조회
  const { data: migrationStatus, isLoading: migrationLoading, refetch: refetchMigration } = useQuery<MigrationStatus | null>({
    queryKey: ['migration-status'],
    queryFn: () => migrationApi.getStatus().catch(() => null),
    retry: 1,
  })

  // 마이그레이션 실행 mutation
  const runMigrationMutation = useMutation({
    mutationFn: () => migrationApi.runMigrations(),
    onSuccess: (data) => {
      if (data.applied.length > 0) {
        toast.success(`${data.applied.length}개 마이그레이션이 적용되었습니다.`)
      } else {
        toast.info('적용할 마이그레이션이 없습니다.')
      }
      queryClient.invalidateQueries({ queryKey: ['migration-status'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 시간 포맷팅
  const formatTime = (timestamp: string | null | undefined) => {
    if (!timestamp) return '기록 없음'
    try {
      const date = new Date(timestamp)
      return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timestamp
    }
  }

  return (
    <>
      {/* 시스템 상태 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📊 시스템 상태</h3>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center justify-between animate-pulse">
                <div className="h-4 w-24 bg-muted rounded" />
                <div className="h-6 w-20 bg-muted rounded-full" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <span className="font-medium">스케줄러 상태</span>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                systemStatus?.scheduler_status === 'running'
                  ? 'bg-green-500/10 text-green-500'
                  : 'bg-yellow-500/10 text-yellow-500'
              }`}>
                {systemStatus?.scheduler_status === 'running' ? '실행 중' : systemStatus?.scheduler_status || 'unknown'}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <span className="font-medium">마지막 Pathfinder 실행</span>
              <span className="text-sm text-muted-foreground">
                {formatTime(systemStatus?.last_pathfinder_run)}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <span className="font-medium">마지막 순위 체크</span>
              <span className="text-sm text-muted-foreground">
                {formatTime(systemStatus?.last_rank_check)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 시스템 진단 정보 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">🔧 시스템 진단</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-3 mb-2">
              <HardDrive className="w-5 h-5 text-blue-500" />
              <span className="font-medium">데이터베이스</span>
            </div>
            <div className="text-2xl font-bold">{backupStatus?.db_size_mb || 0} MB</div>
            <div className="text-xs text-muted-foreground mt-1">
              현재 DB 용량
            </div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-3 mb-2">
              <Database className="w-5 h-5 text-green-500" />
              <span className="font-medium">백업 상태</span>
            </div>
            <div className={`text-2xl font-bold ${
              backupStatus?.warning_level === 'critical' ? 'text-red-500' :
              backupStatus?.warning_level === 'warning' ? 'text-yellow-500' :
              'text-green-500'
            }`}>
              {backupStatus?.total_backups || 0}개
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              저장된 백업 파일
            </div>
          </div>
        </div>
      </div>

      {/* 유용한 명령어 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">💻 유용한 명령어</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <div className="font-medium mb-2">Pathfinder 실행</div>
            <code className="text-sm block bg-background p-2 rounded">
              python pathfinder_v3_complete.py --save-db
            </code>
          </div>
          <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
            <div className="font-medium mb-2">순위 스캔 실행</div>
            <code className="text-sm block bg-background p-2 rounded">
              python place_sniper_v3.py
            </code>
          </div>
          <div className="p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg">
            <div className="font-medium mb-2">웹 서버 실행</div>
            <code className="text-sm block bg-background p-2 rounded">
              build_and_run.bat
            </code>
          </div>
          <div className="p-4 bg-orange-500/10 border border-orange-500/30 rounded-lg">
            <div className="font-medium mb-2">수동 DB 백업</div>
            <code className="text-sm block bg-background p-2 rounded">
              python db_backup.py
            </code>
          </div>
        </div>
      </div>

      {/* DB 마이그레이션 관리 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <FileCode className="w-5 h-5 text-blue-500" />
            DB 마이그레이션
          </h3>
          <IconButton
            icon={<RefreshCw className="w-4 h-4" />}
            onClick={() => refetchMigration()}
            size="sm"
            title="새로고침"
          />
        </div>

        {migrationLoading ? (
          <div className="text-center py-4 text-muted-foreground">로딩 중...</div>
        ) : migrationStatus ? (
          <div className="space-y-4">
            {/* 마이그레이션 요약 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-muted/50 rounded-lg text-center">
                <div className="text-2xl font-bold">{migrationStatus.total_migrations}</div>
                <div className="text-xs text-muted-foreground">전체</div>
              </div>
              <div className="p-3 bg-green-500/10 rounded-lg text-center">
                <div className="text-2xl font-bold text-green-600">{migrationStatus.applied_count}</div>
                <div className="text-xs text-muted-foreground">적용됨</div>
              </div>
              <div className="p-3 bg-yellow-500/10 rounded-lg text-center">
                <div className="text-2xl font-bold text-yellow-600">{migrationStatus.pending_count}</div>
                <div className="text-xs text-muted-foreground">대기중</div>
              </div>
              <div className="p-3 bg-blue-500/10 rounded-lg text-center">
                <div className="text-sm font-medium text-blue-600">{migrationStatus.current_version || 'N/A'}</div>
                <div className="text-xs text-muted-foreground">현재 버전</div>
              </div>
            </div>

            {/* 대기중 마이그레이션 */}
            {migrationStatus.pending && migrationStatus.pending.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-yellow-600">대기중인 마이그레이션</h4>
                <div className="space-y-1">
                  {migrationStatus.pending.map((m) => (
                    <div key={m.version} className="flex items-center gap-2 p-2 bg-yellow-500/10 rounded text-sm">
                      <AlertTriangle className="w-4 h-4 text-yellow-500" />
                      <span className="font-mono">{m.version}</span>
                      <span className="text-muted-foreground">- {m.description}</span>
                    </div>
                  ))}
                </div>
                <Button
                  variant="primary"
                  onClick={() => runMigrationMutation.mutate()}
                  loading={runMigrationMutation.isPending}
                  icon={<Play className="w-4 h-4" />}
                  className="mt-2"
                >
                  마이그레이션 실행
                </Button>
              </div>
            )}

            {/* 최근 적용된 마이그레이션 */}
            {migrationStatus.applied && migrationStatus.applied.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-green-600">최근 적용된 마이그레이션</h4>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {migrationStatus.applied.slice(-5).reverse().map((m) => (
                    <div key={m.version} className="flex items-center gap-2 p-2 bg-green-500/10 rounded text-sm">
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="font-mono">{m.version}</span>
                      <span className="text-muted-foreground">- {m.description}</span>
                      {m.applied_at && (
                        <span className="ml-auto text-xs text-muted-foreground">
                          {new Date(m.applied_at).toLocaleString('ko-KR')}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {migrationStatus.pending_count === 0 && (
              <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-sm text-green-600 flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                모든 마이그레이션이 적용되었습니다.
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-4 text-red-500">마이그레이션 상태를 불러올 수 없습니다.</div>
        )}
      </div>
    </>
  )
}
