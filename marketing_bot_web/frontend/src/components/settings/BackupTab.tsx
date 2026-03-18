/**
 * 데이터베이스 백업 탭 컴포넌트
 * 백업 생성, 복구, 무결성 검사, DB 최적화
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { backupApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import { ConfirmModal } from '@/components/ui/Modal'
import { getErrorMessage } from '@/utils/errorMessages'
import { HardDrive, Database, RotateCcw } from 'lucide-react'

interface BackupFile {
  filename: string
  size_kb: number
  created: string
}

interface BackupStatus {
  days_since_backup?: number | null
  warning_level?: 'critical' | 'warning' | 'ok'
  latest_backup?: {
    created: string
    size_kb: number
  }
  db_size_mb?: number
  total_backups?: number
  backups?: BackupFile[]
}

interface BackupTabProps {
  onMessage: (message: { type: 'success' | 'error'; text: string }) => void
}

export default function BackupTab({ onMessage }: BackupTabProps) {
  const queryClient = useQueryClient()
  const [backupToRestore, setBackupToRestore] = useState<string | null>(null)

  // 백업 상태 조회
  const { data: backupStatus, isLoading: backupLoading } = useQuery<BackupStatus | null>({
    queryKey: ['backup-status'],
    queryFn: () => backupApi.getStatus().catch(() => null),
    refetchInterval: 60000,
    retry: 1,
  })

  // 수동 백업 생성
  const createBackupMutation = useMutation({
    mutationFn: backupApi.createBackup,
    onSuccess: () => {
      onMessage({ type: 'success', text: '백업이 완료되었습니다.' })
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // 무결성 검사
  const integrityCheckMutation = useMutation({
    mutationFn: backupApi.checkIntegrity,
    onSuccess: (data) => {
      onMessage({
        type: data.integrity_ok ? 'success' : 'error',
        text: data.message,
      })
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // VACUUM 최적화
  const vacuumMutation = useMutation({
    mutationFn: backupApi.vacuum,
    onSuccess: (data) => {
      onMessage({
        type: data.success ? 'success' : 'error',
        text: data.success ? `${data.message} (${data.saved_kb}KB 절약)` : data.message,
      })
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // 백업 복구
  const restoreMutation = useMutation({
    mutationFn: backupApi.restoreBackup,
    onSuccess: (data) => {
      onMessage({
        type: 'success',
        text: `${data.message} (복구 전 백업: ${data.pre_restore_backup})`,
      })
      setBackupToRestore(null)
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
      setBackupToRestore(null)
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

  // 경과 일수 텍스트
  const getDaysText = (days: number | null | undefined) => {
    if (days === null || days === undefined) return '백업 없음'
    if (days === 0) return '오늘'
    if (days === 1) return '어제'
    return `${days}일 전`
  }

  // 경고 레벨 색상
  const getWarningColor = (level: string | undefined) => {
    switch (level) {
      case 'critical':
        return 'bg-red-500/10 border-red-500/30 text-red-500'
      case 'warning':
        return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-500'
      default:
        return 'bg-green-500/10 border-green-500/30 text-green-500'
    }
  }

  const isActionPending = createBackupMutation.isPending || integrityCheckMutation.isPending || vacuumMutation.isPending || restoreMutation.isPending

  return (
    <>
      {/* 백업 복구 확인 모달 */}
      <ConfirmModal
        isOpen={backupToRestore !== null}
        onClose={() => setBackupToRestore(null)}
        onConfirm={() => backupToRestore && restoreMutation.mutate(backupToRestore)}
        title="⚠️ 데이터베이스 복구"
        message={`"${backupToRestore}"에서 데이터베이스를 복구하시겠습니까?\n\n현재 데이터베이스가 선택한 백업으로 덮어씌워집니다.\n복구 전에 현재 상태의 백업이 자동으로 생성됩니다.`}
        confirmText="복구 실행"
        cancelText="취소"
        variant="danger"
        loading={restoreMutation.isPending}
      />

      {/* 데이터베이스 백업 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">💾 데이터베이스 백업</h3>

        {backupLoading ? (
          <div className="animate-pulse space-y-4">
            <div className="h-20 bg-muted rounded-lg" />
            <div className="h-32 bg-muted rounded-lg" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* 백업 상태 요약 */}
            <div className={`p-4 rounded-lg border ${getWarningColor(backupStatus?.warning_level)}`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium">마지막 백업</span>
                <span className="font-bold">
                  {getDaysText(backupStatus?.days_since_backup)}
                </span>
              </div>
              {backupStatus?.latest_backup && (
                <div className="text-sm opacity-80">
                  {formatTime(backupStatus.latest_backup.created)} ({backupStatus.latest_backup.size_kb}KB)
                </div>
              )}
              {backupStatus?.warning_level === 'critical' && (
                <div className="mt-2 text-sm font-medium">
                  ⚠️ 7일 이상 백업이 없습니다. 즉시 백업을 생성하세요!
                </div>
              )}
              {backupStatus?.warning_level === 'warning' && (
                <div className="mt-2 text-sm font-medium">
                  ⚠️ 3일 이상 백업이 없습니다. 백업을 권장합니다.
                </div>
              )}
            </div>

            {/* 데이터베이스 정보 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="text-sm text-muted-foreground">현재 DB 크기</div>
                <div className="text-2xl font-bold">{backupStatus?.db_size_mb || 0} MB</div>
              </div>
              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="text-sm text-muted-foreground">백업 파일 수</div>
                <div className="text-2xl font-bold">{backupStatus?.total_backups || 0}개</div>
              </div>
            </div>

            {/* 액션 버튼들 */}
            <div className="flex flex-wrap gap-3">
              <Button
                variant="primary"
                onClick={() => createBackupMutation.mutate()}
                disabled={isActionPending}
                loading={createBackupMutation.isPending}
                icon={<HardDrive size={16} />}
              >
                지금 백업
              </Button>

              <Button
                variant="secondary"
                onClick={() => integrityCheckMutation.mutate()}
                disabled={isActionPending}
                loading={integrityCheckMutation.isPending}
                icon={<Database size={16} />}
              >
                무결성 검사
              </Button>

              <Button
                variant="secondary"
                onClick={() => vacuumMutation.mutate()}
                disabled={isActionPending}
                loading={vacuumMutation.isPending}
                icon={<RotateCcw size={16} />}
              >
                DB 최적화
              </Button>
            </div>

            {/* 최근 백업 목록 */}
            {backupStatus?.backups && backupStatus.backups.length > 0 && (
              <div className="mt-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-medium">최근 백업</div>
                  <div className="text-xs text-muted-foreground">클릭하여 복구</div>
                </div>
                <div className="space-y-2">
                  {backupStatus.backups.map((backup, index) => (
                    <div
                      key={backup.filename}
                      className="flex items-center justify-between p-2 bg-muted/30 rounded text-sm group hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span>{index === 0 ? '🟢' : '⚪'}</span>
                        <span className="font-mono text-xs">{backup.filename}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">{backup.size_kb}KB</span>
                        <IconButton
                          icon={<RotateCcw className="w-4 h-4" />}
                          onClick={() => setBackupToRestore(backup.filename)}
                          disabled={isActionPending}
                          size="sm"
                          title="이 백업에서 복구"
                          className="opacity-0 group-hover:opacity-100 hover:bg-orange-500/10 text-orange-500"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
