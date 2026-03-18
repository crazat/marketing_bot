/**
 * Migration API - 데이터베이스 마이그레이션 관리
 */
import { api } from './base'

// 타입 정의
export interface MigrationInfo {
  version: string
  description: string
  applied_at: string
}

export interface MigrationStatus {
  current_version: string | null
  total_migrations: number
  applied_count: number
  pending_count: number
  applied: MigrationInfo[]
  pending: Array<{
    version: string
    description: string
  }>
}

export interface MigrationRunResult {
  applied: Array<{
    version: string
    description: string
    applied_at: string
  }>
  skipped: Array<{
    version: string
    reason: string
  }>
  errors: Array<{
    version: string
    error: string
  }>
}

export interface MigrationHistory {
  history: MigrationInfo[]
  current_version: string | null
  total_applied: number
}

export const migrationApi = {
  // 마이그레이션 상태 조회
  getStatus: async (): Promise<MigrationStatus> => {
    const response = await api.get('/migration/status')
    return response.data?.data || response.data
  },

  // 마이그레이션 실행
  runMigrations: async (): Promise<MigrationRunResult> => {
    const response = await api.post('/migration/run')
    return response.data?.data || response.data
  },

  // 마이그레이션 히스토리 조회
  getHistory: async (): Promise<MigrationHistory> => {
    const response = await api.get('/migration/history')
    return response.data?.data || response.data
  },
}
