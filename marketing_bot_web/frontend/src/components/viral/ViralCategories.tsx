interface ViralCategoriesProps {
  categories: any[]
  selectedCategory: string | null
  onSelectCategory: (category: string | null) => void
}

export default function ViralCategories({
  categories,
  selectedCategory,
  onSelectCategory
}: ViralCategoriesProps) {
  if (!categories || categories.length === 0) return null

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h3 className="text-lg font-semibold mb-4">📊 카테고리별 타겟</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <button
          onClick={() => onSelectCategory(null)}
          className={`
            p-4 rounded-lg border-2 transition-all text-left
            ${selectedCategory === null
              ? 'border-primary bg-primary/10'
              : 'border-border hover:border-primary/50'
            }
          `}
        >
          <div className="font-semibold mb-1">전체</div>
          <div className="text-2xl font-bold">
            {categories.reduce((sum, cat) => sum + cat.count, 0)}
          </div>
        </button>

        {categories.map((cat) => (
          <button
            key={cat.category}
            onClick={() => onSelectCategory(cat.category)}
            className={`
              p-4 rounded-lg border-2 transition-all text-left
              ${selectedCategory === cat.category
                ? 'border-primary bg-primary/10'
                : 'border-border hover:border-primary/50'
              }
            `}
          >
            <div className="font-semibold mb-1 truncate">{cat.category}</div>
            <div className="text-2xl font-bold">{cat.count}</div>
            <div className="text-xs text-muted-foreground mt-1">
              평균 점수: {cat.avg_score}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
