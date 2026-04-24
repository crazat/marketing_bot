interface LeadFilters {
  platform: string
  status: string
  category: string
}

interface Category {
  category: string
  count: number
}

interface LeadFiltersProps {
  filters: LeadFilters
  onFiltersChange: (filters: LeadFilters) => void
  categories: Category[]
}

export default function LeadFilters({ filters, onFiltersChange, categories }: LeadFiltersProps) {
  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h3 className="text-lg font-semibold mb-4">🔍 필터</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label htmlFor="platform-filter" className="block text-sm font-medium mb-2">플랫폼</label>
          <select
            id="platform-filter"
            value={filters.platform}
            onChange={(e) => onFiltersChange({ ...filters, platform: e.target.value })}
            className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            aria-label="플랫폼 필터"
          >
            <option value="">전체</option>
            <option value="youtube">📺 YouTube</option>
            <option value="tiktok">🎵 TikTok</option>
            <option value="naver">🟢 Naver</option>
            <option value="instagram">📸 Instagram</option>
          </select>
        </div>

        <div>
          <label htmlFor="status-filter" className="block text-sm font-medium mb-2">상태</label>
          <select
            id="status-filter"
            value={filters.status}
            onChange={(e) => onFiltersChange({ ...filters, status: e.target.value })}
            className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            aria-label="상태 필터"
          >
            <option value="">전체</option>
            <option value="pending">⏳ 대기</option>
            <option value="contacted">📞 연락함</option>
            <option value="replied">💬 답변받음</option>
            <option value="converted">✅ 전환완료</option>
            <option value="rejected">❌ 거절됨</option>
          </select>
        </div>

        <div>
          <label htmlFor="category-filter" className="block text-sm font-medium mb-2">카테고리</label>
          <select
            id="category-filter"
            value={filters.category}
            onChange={(e) => onFiltersChange({ ...filters, category: e.target.value })}
            className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            aria-label="카테고리 필터"
          >
            <option value="">전체</option>
            {categories?.map((cat) => (
              <option key={cat.category} value={cat.category}>
                {cat.category} ({cat.count})
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
