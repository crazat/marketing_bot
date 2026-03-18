/**
 * Backup API - 데이터베이스 백업 관련
 */

import { api } from './base'

export const backupApi = {
  getStatus: async () => {
    const response = await api.get('/backup/status')
    return response.data
  },

  createBackup: async () => {
    const response = await api.post('/backup/create')
    return response.data
  },

  getList: async () => {
    const response = await api.get('/backup/list')
    return response.data
  },

  checkIntegrity: async () => {
    const response = await api.post('/backup/integrity-check')
    return response.data
  },

  vacuum: async () => {
    const response = await api.post('/backup/vacuum')
    return response.data
  },

  restoreBackup: async (filename: string) => {
    const response = await api.post(`/backup/restore/${filename}`)
    return response.data
  },
}
