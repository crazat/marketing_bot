/**
 * Viral Hunter - 완료 화면
 * 카테고리 작업 완료 통계 표시
 */

import { CompletionStats } from '@/types/viral'

interface CompletionViewProps {
  selectedCategory: string | null
  completionStats: CompletionStats
  onGoHome: () => void
}

export function CompletionView({
  selectedCategory,
  completionStats,
  onGoHome,
}: CompletionViewProps) {
  const totalProcessed = completionStats.approved + completionStats.skipped + completionStats.deleted
  const approvalRate = totalProcessed > 0 ? (completionStats.approved / totalProcessed) * 100 : 0

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="text-center py-8">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-yellow-500 to-green-500 bg-clip-text text-transparent mb-2">
          🎉 축하합니다!
        </h1>
        <p className="text-xl text-muted-foreground">
          '{selectedCategory}' 카테고리의 모든 작업을 완료했습니다!
        </p>
      </div>

      {/* 통계 */}
      <div>
        <h2 className="text-2xl font-bold mb-4">📊 작업 통계</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold">{totalProcessed}</div>
            <div className="text-sm text-muted-foreground mt-2">총 처리</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-green-500">{completionStats.approved}</div>
            <div className="text-sm text-muted-foreground mt-2">✅ 승인</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-blue-500">{completionStats.skipped}</div>
            <div className="text-sm text-muted-foreground mt-2">⏭️ 건너뜀</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-6 text-center">
            <div className="text-4xl font-bold text-red-500">{completionStats.deleted}</div>
            <div className="text-sm text-muted-foreground mt-2">🗑️ 삭제</div>
          </div>
        </div>
      </div>

      {/* 승인율 */}
      {totalProcessed > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">승인율: {approvalRate.toFixed(1)}%</h3>
          <div className="w-full bg-muted rounded-full h-4">
            <div
              className="bg-gradient-to-r from-yellow-500 to-green-500 h-4 rounded-full transition-all"
              style={{ width: `${approvalRate}%` }}
            />
          </div>
        </div>
      )}

      {/* 홈으로 버튼 */}
      <button
        onClick={onGoHome}
        className="w-full py-4 bg-primary text-primary-foreground rounded-lg font-semibold hover:bg-primary/90"
      >
        🏠 홈으로 돌아가기
      </button>
    </div>
  )
}
