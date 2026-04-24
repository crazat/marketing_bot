import { Calendar, TrendingUp } from 'lucide-react'
import { getSeasonHint } from '@/utils/seasonality'
import { useNavigate } from 'react-router-dom'

/**
 * [BB6] 계절성 힌트 — Dashboard 하단 조용히 노출
 *
 * 월별 트렌딩 카테고리를 알려 새로운 키워드 탐색 기회 제시.
 * 한의원 도메인 특화. 과거 데이터 누적 시 학습 기반으로 확장 가능.
 */
export default function SeasonalityHint() {
  const navigate = useNavigate()
  const hint = getSeasonHint()
  if (hint.trending.length === 0) return null

  return (
    <section
      aria-label="계절성 힌트"
      className="relative bg-card border border-border p-5 md:p-6 overflow-hidden"
    >
      <span
        aria-hidden
        className="absolute right-4 top-1 text-[7rem] leading-none font-display text-foreground/[0.03] select-none pointer-events-none"
      >
        季
      </span>
      <div className="relative">
        <div className="caps text-muted-foreground mb-2 flex items-center gap-1.5">
          <Calendar className="w-3 h-3" aria-hidden />
          <span>{hint.month}월 계절성 · Seasonal</span>
        </div>
        <h3 className="font-display text-lg md:text-xl leading-tight mb-2">
          이 시기 주목 카테고리
        </h3>
        <p className="text-xs text-muted-foreground mb-3">{hint.note}</p>
        <div className="flex flex-wrap gap-2">
          {hint.trending.map((cat) => (
            <button
              key={cat}
              onClick={() => navigate(`/viral?category=${encodeURIComponent(cat)}`)}
              className="group inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-primary/40 bg-primary/5 text-primary hover:bg-primary/10 transition-colors"
              title={`${cat} 타겟 보기`}
            >
              <TrendingUp className="w-3 h-3" aria-hidden />
              <span>{cat}</span>
              <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
