interface PathfinderControlsProps {
  onRun: (mode: 'total_war' | 'legion') => void
  isRunning: boolean
  selectedMode: 'total_war' | 'legion'
  onModeChange: (mode: 'total_war' | 'legion') => void
}

export default function PathfinderControls({
  onRun,
  isRunning,
  selectedMode,
  onModeChange
}: PathfinderControlsProps) {
  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h3 className="text-lg font-semibold mb-4">⚡ Pathfinder 실행</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Total War */}
        <div
          className={`
            p-6 rounded-lg border-2 cursor-pointer transition-all
            ${selectedMode === 'total_war'
              ? 'border-blue-500 bg-blue-500/10'
              : 'border-border hover:border-blue-500/50'
            }
          `}
          onClick={() => onModeChange('total_war')}
        >
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">⚔️</span>
            <h4 className="text-lg font-bold">Total War</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            자동완성 + SERP 분석 기반 키워드 발굴
          </p>
          <ul className="text-sm space-y-1 text-muted-foreground">
            <li>• 네이버 자동완성 API</li>
            <li>• SERP 난이도/기회 분석</li>
            <li>• S/A/B/C 등급 자동 분류</li>
          </ul>
        </div>

        {/* LEGION */}
        <div
          className={`
            p-6 rounded-lg border-2 cursor-pointer transition-all
            ${selectedMode === 'legion'
              ? 'border-purple-500 bg-purple-500/10'
              : 'border-border hover:border-purple-500/50'
            }
          `}
          onClick={() => onModeChange('legion')}
        >
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">🚀</span>
            <h4 className="text-lg font-bold">LEGION MODE</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            6단계 확장 전략으로 대량 키워드 수집
          </p>
          <ul className="text-sm space-y-1 text-muted-foreground">
            <li>• Round 1-6: 체계적 확장</li>
            <li>• 지역/의도/경쟁사 분석</li>
            <li>• 목표: 500개 S/A급 키워드</li>
          </ul>
        </div>
      </div>

      {/* 실행 버튼 */}
      <div className="mt-6 flex gap-4">
        <button
          onClick={() => onRun(selectedMode)}
          disabled={isRunning}
          className={`
            flex-1 px-6 py-3 rounded-lg font-semibold transition-all
            ${isRunning
              ? 'bg-muted text-muted-foreground cursor-not-allowed'
              : selectedMode === 'total_war'
                ? 'bg-blue-500 hover:bg-blue-600 text-white'
                : 'bg-purple-500 hover:bg-purple-600 text-white'
            }
          `}
        >
          {isRunning ? (
            <>
              <span className="inline-block animate-spin mr-2">⚙️</span>
              실행 중...
            </>
          ) : (
            <>
              {selectedMode === 'total_war' ? '⚔️ Total War 실행' : '🚀 LEGION MODE 실행'}
            </>
          )}
        </button>
      </div>

      {isRunning && (
        <div className="mt-4 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <p className="text-sm text-yellow-500">
            ⚡ Pathfinder가 실행 중입니다. 몇 분 정도 소요될 수 있습니다.
          </p>
        </div>
      )}
    </div>
  )
}
