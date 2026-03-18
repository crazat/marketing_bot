import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { pathfinderApi } from '@/services/api'
import Button from '@/components/ui/Button'
import { Rocket, Copy } from 'lucide-react'

interface KeywordUtilizationTabProps {
  stats: any
}

export default function KeywordUtilizationTab({ stats }: KeywordUtilizationTabProps) {
  const [activeSubTab, setActiveSubTab] = useState('title-generator')

  return (
    <div className="space-y-6">
      {/* 서브 탭 */}
      <div className="flex gap-2 border-b border-border">
        {[
          { id: 'title-generator', label: '✍️ 블로그 제목 생성', icon: '✍️' },
          { id: 'content-ideas', label: '💡 콘텐츠 아이디어', icon: '💡' },
          { id: 'keyword-grouping', label: '📦 키워드 그룹화', icon: '📦' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveSubTab(tab.id)}
            className={`
              px-4 py-2 font-medium transition-colors relative text-sm
              ${activeSubTab === tab.id
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
              }
            `}
          >
            {tab.label}
            {activeSubTab === tab.id && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        ))}
      </div>

      {/* 서브 탭 컨텐츠 */}
      {activeSubTab === 'title-generator' && <BlogTitleGenerator stats={stats} />}
      {activeSubTab === 'content-ideas' && <ContentIdeas stats={stats} />}
      {activeSubTab === 'keyword-grouping' && <KeywordGrouping stats={stats} />}
    </div>
  )
}

// 블로그 제목 생성기
function BlogTitleGenerator({ stats }: { stats: any }) {
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([])
  const [titleStyle, setTitleStyle] = useState('정보형')
  const [includeRegion, setIncludeRegion] = useState(true)
  const [includeEmoji, setIncludeEmoji] = useState(false)
  const [generatedTitles, setGeneratedTitles] = useState<string[]>([])
  const [isGenerating, setIsGenerating] = useState(false)

  // S/A급 키워드 조회
  const { data: saKeywords } = useQuery({
    queryKey: ['pathfinder-sa-keywords'],
    queryFn: () => pathfinderApi.getKeywords({
      limit: 1000,
    }),
    select: (data) => data ? data.filter((kw: any) => ['S', 'A'].includes(kw.grade)) : [],
    retry: 1,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  const titleStyles = {
    '정보형': '~하는 방법, ~알아보기, ~총정리',
    '후기형': '~후기, ~경험담, ~솔직리뷰',
    '비교형': '~vs~, ~차이점, ~비교분석',
    '리스트형': '~TOP5, ~추천 베스트, ~필수 체크리스트',
    '질문형': '~할까요?, ~어떨까?, ~괜찮을까?',
    '문제해결형': '~고민 해결, ~때문에 고민이라면, ~걱정되시나요?',
  }

  // 필터링된 키워드
  const filteredKeywords = useMemo(() => {
    if (!saKeywords) return []
    if (!selectedCategory) return saKeywords
    return saKeywords.filter((kw: any) => kw.category === selectedCategory)
  }, [saKeywords, selectedCategory])

  // 키워드 선택 토글
  const toggleKeyword = (keyword: string) => {
    if (selectedKeywords.includes(keyword)) {
      setSelectedKeywords(selectedKeywords.filter(k => k !== keyword))
    } else {
      if (selectedKeywords.length < 5) {
        setSelectedKeywords([...selectedKeywords, keyword])
      } else {
        alert('최대 5개까지만 선택 가능합니다.')
      }
    }
  }

  // 제목 생성 (클라이언트 사이드 템플릿 기반)
  const handleGenerateTitles = () => {
    if (selectedKeywords.length === 0) {
      alert('키워드를 선택해주세요.')
      return
    }

    setIsGenerating(true)

    // 간단한 템플릿 기반 생성 (실제로는 백엔드 AI API 호출 권장)
    const titles: string[] = []
    const mainKeyword = selectedKeywords[0]
    const region = includeRegion ? '청주 ' : ''
    const emoji = includeEmoji ? '✨ ' : ''

    switch (titleStyle) {
      case '정보형':
        titles.push(`${emoji}${region}${mainKeyword} 완벽 가이드`)
        titles.push(`${emoji}${region}${mainKeyword} 알아보기 - 2026년 최신`)
        titles.push(`${emoji}${region}${mainKeyword} 총정리 | 효과부터 비용까지`)
        titles.push(`${emoji}${region}${mainKeyword} 제대로 알고 시작하기`)
        titles.push(`${emoji}${mainKeyword} 전문가가 알려주는 핵심 정보`)
        break
      case '후기형':
        titles.push(`${emoji}${region}${mainKeyword} 3개월 후기`)
        titles.push(`${emoji}${region}${mainKeyword} 실제 경험담`)
        titles.push(`${emoji}${mainKeyword} 솔직 리뷰 | 장단점 공개`)
        titles.push(`${emoji}${region}${mainKeyword} 직접 받아본 후기`)
        titles.push(`${emoji}${mainKeyword} 후기 모음 | 실제 효과는?`)
        break
      case '비교형':
        titles.push(`${emoji}${mainKeyword} vs 일반 치료 차이점`)
        titles.push(`${emoji}${region}${mainKeyword} 비교 분석`)
        titles.push(`${emoji}${mainKeyword} 장단점 비교`)
        titles.push(`${emoji}${mainKeyword} 어떤 게 더 좋을까?`)
        titles.push(`${emoji}${mainKeyword} 선택 가이드`)
        break
      case '리스트형':
        titles.push(`${emoji}${region}${mainKeyword} 추천 TOP5`)
        titles.push(`${emoji}${mainKeyword} 전 필수 체크리스트 7가지`)
        titles.push(`${emoji}${region}${mainKeyword} 베스트 추천`)
        titles.push(`${emoji}${mainKeyword} 시작 전 꼭 알아야 할 5가지`)
        titles.push(`${emoji}${region}${mainKeyword} 성공 비결 7가지`)
        break
      case '질문형':
        titles.push(`${emoji}${region}${mainKeyword}, 효과 있을까요?`)
        titles.push(`${emoji}${mainKeyword} 받아도 될까?`)
        titles.push(`${emoji}${region}${mainKeyword} 괜찮을까요?`)
        titles.push(`${emoji}${mainKeyword} 정말 도움이 될까?`)
        titles.push(`${emoji}${region}${mainKeyword} 궁금증 해결`)
        break
      case '문제해결형':
        titles.push(`${emoji}${mainKeyword} 고민이라면 꼭 읽어보세요`)
        titles.push(`${emoji}${mainKeyword} 때문에 걱정되시나요?`)
        titles.push(`${emoji}${region}${mainKeyword} 고민 해결법`)
        titles.push(`${emoji}${mainKeyword} 실패 없이 성공하는 방법`)
        titles.push(`${emoji}${mainKeyword} 걱정 해결 가이드`)
        break
    }

    // 2차 키워드 조합
    if (selectedKeywords.length > 1) {
      const secondKeyword = selectedKeywords[1]
      titles.push(`${emoji}${region}${mainKeyword} + ${secondKeyword} 함께 하면?`)
      titles.push(`${emoji}${mainKeyword}와 ${secondKeyword} 동시 진행 후기`)
    }

    setGeneratedTitles(titles.slice(0, 10))
    setIsGenerating(false)
  }

  // 전체 복사
  const handleCopyAll = () => {
    const text = generatedTitles.join('\n')
    navigator.clipboard.writeText(text)
    alert('전체 제목이 클립보드에 복사되었습니다.')
  }

  return (
    <div className="space-y-6">
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-2">✍️ 블로그 제목 생성기</h3>
        <p className="text-sm text-muted-foreground mb-4">
          S/A급 키워드를 선택하면 클릭을 유도하는 매력적인 블로그 제목을 생성합니다.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 좌측: 설정 */}
          <div className="space-y-4">
            {/* 카테고리 선택 */}
            <div>
              <label className="block text-sm font-medium mb-2">📂 카테고리</label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md"
              >
                <option value="">전체</option>
                {stats?.categories && Object.keys(stats.categories).map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            {/* 키워드 선택 */}
            <div>
              <label className="block text-sm font-medium mb-2">
                🔑 키워드 선택 (최대 5개) - {selectedKeywords.length}/5
              </label>
              <div className="border border-border rounded-md p-3 max-h-48 overflow-y-auto bg-background">
                {filteredKeywords.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    S/A급 키워드가 없습니다.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {filteredKeywords.slice(0, 50).map((kw: any) => (
                      <button
                        key={kw.keyword}
                        onClick={() => toggleKeyword(kw.keyword)}
                        className={`
                          w-full text-left px-3 py-2 rounded text-sm transition-colors
                          ${selectedKeywords.includes(kw.keyword)
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-muted'
                          }
                        `}
                      >
                        {kw.keyword} ({kw.grade}급, {kw.search_volume?.toLocaleString() || 0})
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 제목 스타일 */}
            <div>
              <label className="block text-sm font-medium mb-2">📝 제목 스타일</label>
              <select
                value={titleStyle}
                onChange={(e) => setTitleStyle(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md"
              >
                {Object.entries(titleStyles).map(([style, example]) => (
                  <option key={style} value={style}>
                    {style} ({example})
                  </option>
                ))}
              </select>
            </div>

            {/* 추가 옵션 */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeRegion}
                  onChange={(e) => setIncludeRegion(e.target.checked)}
                  className="w-4 h-4"
                />
                <span className="text-sm">지역명 포함 (청주)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeEmoji}
                  onChange={(e) => setIncludeEmoji(e.target.checked)}
                  className="w-4 h-4"
                />
                <span className="text-sm">이모지 포함</span>
              </label>
            </div>

            {/* 생성 버튼 */}
            <Button
              variant="primary"
              size="lg"
              fullWidth
              onClick={handleGenerateTitles}
              disabled={selectedKeywords.length === 0}
              loading={isGenerating}
              icon={<Rocket size={16} />}
            >
              제목 생성
            </Button>
          </div>

          {/* 우측: 결과 */}
          <div className="space-y-4">
            {generatedTitles.length === 0 ? (
              <div className="border border-border rounded-lg p-8 text-center">
                <p className="text-4xl mb-4">✍️</p>
                <p className="text-muted-foreground">
                  키워드를 선택하고 '제목 생성' 버튼을 클릭하세요.
                </p>
                {filteredKeywords.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-semibold mb-2">📊 S/A급 키워드 미리보기</p>
                    <div className="text-left space-y-1 max-h-40 overflow-y-auto">
                      {filteredKeywords.slice(0, 10).map((kw: any) => (
                        <div key={kw.keyword} className="text-xs text-muted-foreground">
                          • {kw.keyword} ({kw.grade}급, {kw.search_volume?.toLocaleString() || 0})
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">📋 생성된 제목 ({generatedTitles.length}개)</h4>
                  <Button
                    variant="success"
                    size="sm"
                    onClick={handleCopyAll}
                    icon={<Copy size={14} />}
                  >
                    전체 복사
                  </Button>
                </div>

                <div className="space-y-2">
                  {generatedTitles.map((title, index) => (
                    <div
                      key={index}
                      className="p-3 bg-muted rounded-lg hover:bg-muted/80 transition-colors cursor-pointer"
                      onClick={() => {
                        navigator.clipboard.writeText(title)
                        alert(`"${title}" 복사됨`)
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <span className="text-xs text-muted-foreground min-w-6">{index + 1}.</span>
                        <span className="text-sm flex-1">{title}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                  <p className="text-xs text-blue-500">
                    💡 제목을 클릭하면 클립보드에 복사됩니다.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// 콘텐츠 아이디어
function ContentIdeas({ stats: _stats }: { stats: any }) {
  void _stats // reserved for future use
  const { data: saKeywords } = useQuery({
    queryKey: ['pathfinder-sa-keywords-ideas'],
    queryFn: () => pathfinderApi.getKeywords({
      limit: 1000,
    }),
    select: (data) => data ? data.filter((kw: any) => ['S', 'A'].includes(kw.grade)) : [],
    retry: 1,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // 카테고리별 그룹화
  const groupedByCategory = useMemo(() => {
    if (!saKeywords) return {}

    const grouped: Record<string, any[]> = {}
    saKeywords.forEach((kw: any) => {
      const cat = kw.category || '기타'
      if (!grouped[cat]) grouped[cat] = []
      grouped[cat].push(kw)
    })

    return grouped
  }, [saKeywords])

  return (
    <div className="space-y-6">
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-2">💡 콘텐츠 아이디어</h3>
        <p className="text-sm text-muted-foreground mb-4">
          카테고리별 S/A급 키워드를 활용한 블로그 콘텐츠 아이디어입니다.
        </p>

        {Object.keys(groupedByCategory).length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-4xl mb-4">💡</p>
            <p>S/A급 키워드가 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(groupedByCategory).map(([category, keywords]) => (
              <div key={category} className="border border-border rounded-lg p-4">
                <h4 className="font-semibold mb-3">
                  📂 {category} ({keywords.length}개 키워드)
                </h4>

                <div className="space-y-3">
                  <div className="bg-muted/50 rounded p-3">
                    <p className="text-sm font-medium mb-2">📝 추천 콘텐츠 주제:</p>
                    <ul className="text-sm space-y-1 ml-4">
                      <li>• {category} 완벽 가이드 (종합편)</li>
                      <li>• {category} 자주 묻는 질문 TOP 10</li>
                      <li>• {category} 효과적인 방법과 주의사항</li>
                      <li>• {category} 실제 사례 및 후기 모음</li>
                    </ul>
                  </div>

                  <div>
                    <p className="text-xs font-medium mb-2 text-muted-foreground">활용 가능한 키워드:</p>
                    <div className="flex flex-wrap gap-2">
                      {keywords.slice(0, 10).map((kw: any) => (
                        <span
                          key={kw.keyword}
                          className="text-xs px-2 py-1 rounded bg-primary/10 text-primary"
                        >
                          {kw.keyword}
                        </span>
                      ))}
                      {keywords.length > 10 && (
                        <span className="text-xs text-muted-foreground">
                          +{keywords.length - 10}개
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// 키워드 그룹화
function KeywordGrouping({ stats: _stats }: { stats: any }) {
  void _stats // reserved for future use
  const { data: clusters } = useQuery({
    queryKey: ['pathfinder-clusters-util'],
    queryFn: pathfinderApi.getClusters,
    retry: 1,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  return (
    <div className="space-y-6">
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-2">📦 키워드 그룹화</h3>
        <p className="text-sm text-muted-foreground mb-4">
          관련 키워드를 그룹화하여 1개 블로그 글로 여러 키워드를 동시 공략할 수 있습니다.
        </p>

        {!clusters || clusters.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-4xl mb-4">📦</p>
            <p>클러스터 데이터가 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <p className="text-sm text-blue-500">
                💡 총 {clusters.length}개 클러스터에 {clusters.reduce((sum: number, c: any) => sum + c.keyword_count, 0)}개 키워드가 포함되어 있습니다.
              </p>
            </div>

            {clusters.slice(0, 10).map((cluster: any, index: number) => (
              <div key={index} className="border border-border rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="font-semibold">
                      📦 {cluster.cluster_name}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      {cluster.keyword_count}개 키워드 • 검색량 {cluster.total_search_volume?.toLocaleString() || 0}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-primary">
                      품질: {cluster.avg_quality?.toFixed(1) || 0}/4.0
                    </div>
                  </div>
                </div>

                <div className="bg-muted/50 rounded p-3 mb-3">
                  <p className="text-sm font-medium mb-2">📝 추천 글 제목:</p>
                  <p className="text-sm">{cluster.cluster_name} 완벽 가이드 | 2026년 최신</p>
                </div>

                <div>
                  <p className="text-xs font-medium mb-2 text-muted-foreground">포함할 키워드:</p>
                  <div className="flex flex-wrap gap-2">
                    {cluster.keywords?.slice(0, 10).map((kw: string, i: number) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-500"
                      >
                        {kw}
                      </span>
                    ))}
                    {cluster.keyword_count > 10 && (
                      <span className="text-xs text-muted-foreground">
                        +{cluster.keyword_count - 10}개
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
