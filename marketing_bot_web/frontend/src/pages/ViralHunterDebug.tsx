import { useQuery } from '@tanstack/react-query'
import { viralApi } from '@/services/api'

export default function ViralHunterDebug() {
  const { data: stats, error: statsError, isLoading: statsLoading } = useQuery({
    queryKey: ['viral-stats'],
    queryFn: viralApi.getStats,
  })

  const { data: targets, error: targetsError, isLoading: targetsLoading } = useQuery({
    queryKey: ['viral-targets'],
    queryFn: () => viralApi.getTargets('pending', undefined, 10),
  })

  return (
    <div className="p-8 space-y-6">
      <h1 className="text-3xl font-bold">🔍 Viral Hunter 디버그</h1>

      {/* Stats */}
      <div className="bg-card rounded-lg border p-6">
        <h2 className="text-xl font-bold mb-4">📊 Stats API</h2>
        {statsLoading && <p>로딩 중...</p>}
        {statsError && <p className="text-red-500">에러: {String(statsError)}</p>}
        {stats && (
          <pre className="bg-black text-green-400 p-4 rounded overflow-auto">
            {JSON.stringify(stats, null, 2)}
          </pre>
        )}
      </div>

      {/* Targets */}
      <div className="bg-card rounded-lg border p-6">
        <h2 className="text-xl font-bold mb-4">🎯 Targets API</h2>
        {targetsLoading && <p>로딩 중...</p>}
        {targetsError && <p className="text-red-500">에러: {String(targetsError)}</p>}
        {targets && (
          <>
            <p className="mb-2">타겟 개수: {targets.length}</p>
            <pre className="bg-black text-green-400 p-4 rounded overflow-auto max-h-96">
              {JSON.stringify(targets, null, 2)}
            </pre>
          </>
        )}
      </div>
    </div>
  )
}
