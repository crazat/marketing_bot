import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reviewsApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'
import {
  MessageSquare,
  Sparkles,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Minus,
  History,
  FileText,
  RefreshCw,
  Trash2,
  Plus
} from 'lucide-react'

interface Template {
  id: number
  name: string
  content: string
  variables: string[]
  use_count: number
}

interface GeneratedResponse {
  sentiment: string
  response: string
  tone: string
  reviewer_name: string
  generated_at: string
}

export default function ReviewResponseAssistant() {
  const [activeTab, setActiveTab] = useState<'generate' | 'templates' | 'history'>('generate')
  const [reviewContent, setReviewContent] = useState('')
  const [reviewerName, setReviewerName] = useState('')
  const [rating, setRating] = useState<number>(5)
  const [tone, setTone] = useState<'professional' | 'friendly' | 'empathetic'>('professional')
  const [includePromotion, setIncludePromotion] = useState(false)
  const [generatedResponse, setGeneratedResponse] = useState<GeneratedResponse | null>(null)
  const [newTemplateModal, setNewTemplateModal] = useState(false)
  const [newTemplate, setNewTemplate] = useState({
    sentiment: 'positive',
    template_name: '',
    content: ''
  })

  const queryClient = useQueryClient()
  const toast = useToast()

  // 템플릿 조회
  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ['review-templates'],
    queryFn: reviewsApi.getTemplates,
  })

  // 히스토리 조회
  const { data: historyData } = useQuery({
    queryKey: ['review-history'],
    queryFn: () => reviewsApi.getHistory(20),
    enabled: activeTab === 'history',
  })

  // 통계 조회
  const { data: stats } = useQuery({
    queryKey: ['review-stats'],
    queryFn: reviewsApi.getStats,
  })

  // AI 응답 생성
  const generateMutation = useMutation({
    mutationFn: reviewsApi.generateResponse,
    onSuccess: (data) => {
      setGeneratedResponse(data)
      queryClient.invalidateQueries({ queryKey: ['review-history'] })
      queryClient.invalidateQueries({ queryKey: ['review-stats'] })
      toast.success('응답이 생성되었습니다')
    },
    onError: (error: any) => {
      toast.error(`응답 생성 실패: ${error.message || '알 수 없는 오류'}`)
    },
  })

  // 템플릿 생성
  const createTemplateMutation = useMutation({
    mutationFn: reviewsApi.createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-templates'] })
      setNewTemplateModal(false)
      setNewTemplate({ sentiment: 'positive', template_name: '', content: '' })
      toast.success('템플릿이 추가되었습니다')
    },
    onError: () => {
      toast.error('템플릿 추가 실패')
    },
  })

  // 템플릿 사용
  const useTemplateMutation = useMutation({
    mutationFn: reviewsApi.useTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-templates'] })
    },
  })

  // 템플릿 삭제
  const deleteTemplateMutation = useMutation({
    mutationFn: reviewsApi.deleteTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-templates'] })
      toast.success('템플릿이 삭제되었습니다')
    },
  })

  const handleGenerate = () => {
    if (!reviewContent.trim()) {
      toast.error('리뷰 내용을 입력해주세요')
      return
    }

    generateMutation.mutate({
      review_content: reviewContent,
      reviewer_name: reviewerName || undefined,
      rating,
      tone,
      include_promotion: includePromotion,
    })
  }

  const handleCopyResponse = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('클립보드에 복사되었습니다')
  }

  const handleUseTemplate = (template: Template) => {
    let content = template.content
    if (reviewerName) {
      content = content.replace(/{reviewer_name}/g, reviewerName)
    } else {
      content = content.replace(/{reviewer_name}/g, '고객')
    }
    setGeneratedResponse({
      sentiment: 'template',
      response: content,
      tone: 'template',
      reviewer_name: reviewerName || '고객',
      generated_at: new Date().toISOString(),
    })
    useTemplateMutation.mutate(template.id)
    toast.success('템플릿이 적용되었습니다')
  }

  const sentimentIcons = {
    positive: <ThumbsUp className="w-4 h-4 text-green-500" />,
    negative: <ThumbsDown className="w-4 h-4 text-red-500" />,
    neutral: <Minus className="w-4 h-4 text-gray-500" />,
  }

  const sentimentLabels = {
    positive: '긍정',
    negative: '부정',
    neutral: '중립',
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary" />
            리뷰 응답 도우미
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            AI가 리뷰에 맞는 응답 초안을 생성해드립니다.
            <span className="text-primary font-medium"> 생성된 응답을 복사하여 네이버 플레이스에 붙여넣으세요.</span>
          </p>
        </div>
        {stats && (
          <div className="flex items-center gap-4 text-sm">
            <div className="text-center">
              <div className="font-bold text-primary">{stats.total_responses}</div>
              <div className="text-muted-foreground">총 응답</div>
            </div>
            <div className="text-center">
              <div className="font-bold text-green-500">{stats.today_count}</div>
              <div className="text-muted-foreground">오늘</div>
            </div>
          </div>
        )}
      </div>

      {/* 탭 */}
      <div className="flex gap-2 border-b border-border">
        {[
          { id: 'generate', label: 'AI 응답 생성', icon: Sparkles },
          { id: 'templates', label: '템플릿', icon: FileText },
          { id: 'history', label: '히스토리', icon: History },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-3 font-medium transition-colors relative ${
              activeTab === tab.id
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
            {activeTab === tab.id && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        ))}
      </div>

      {/* AI 응답 생성 탭 */}
      {activeTab === 'generate' && (
        <div className="grid md:grid-cols-2 gap-6">
          {/* 입력 영역 */}
          <div className="bg-card rounded-lg border border-border p-6">
            <h3 className="font-bold mb-4">리뷰 정보 입력</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">리뷰 내용 *</label>
                <textarea
                  value={reviewContent}
                  onChange={(e) => setReviewContent(e.target.value)}
                  placeholder="응답할 리뷰 내용을 입력하세요..."
                  className="w-full h-32 px-3 py-2 border border-border rounded-lg bg-background resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">리뷰어 이름</label>
                  <input
                    type="text"
                    value={reviewerName}
                    onChange={(e) => setReviewerName(e.target.value)}
                    placeholder="홍길동"
                    className="w-full px-3 py-2 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">평점</label>
                  <select
                    value={rating}
                    onChange={(e) => setRating(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {[5, 4, 3, 2, 1].map((r) => (
                      <option key={r} value={r}>{r}점</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">응답 톤</label>
                <div className="flex gap-2">
                  {[
                    { value: 'professional', label: '전문적' },
                    { value: 'friendly', label: '친근한' },
                    { value: 'empathetic', label: '공감하는' },
                  ].map((t) => (
                    <button
                      key={t.value}
                      onClick={() => setTone(t.value as any)}
                      className={`flex-1 px-3 py-2 rounded-lg border transition-colors ${
                        tone === t.value
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-border hover:bg-muted'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="include-promotion"
                  checked={includePromotion}
                  onChange={(e) => setIncludePromotion(e.target.checked)}
                  className="w-4 h-4 rounded border-border"
                />
                <label htmlFor="include-promotion" className="text-sm">
                  우리 한의원 강점 자연스럽게 언급
                </label>
              </div>

              <Button
                variant="primary"
                fullWidth
                onClick={handleGenerate}
                loading={generateMutation.isPending}
                disabled={!reviewContent.trim()}
                icon={<Sparkles className="w-4 h-4" />}
              >
                AI 응답 생성
              </Button>
            </div>
          </div>

          {/* 결과 영역 */}
          <div className="bg-card rounded-lg border border-border p-6">
            <h3 className="font-bold mb-4">생성된 응답</h3>

            {generatedResponse ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  {sentimentIcons[generatedResponse.sentiment as keyof typeof sentimentIcons]}
                  <span className="text-sm text-muted-foreground">
                    {sentimentLabels[generatedResponse.sentiment as keyof typeof sentimentLabels] || generatedResponse.sentiment}
                  </span>
                  <span className="text-xs px-2 py-0.5 bg-muted rounded">
                    {generatedResponse.tone}
                  </span>
                </div>

                <div className="p-4 bg-muted/50 rounded-lg whitespace-pre-wrap">
                  {generatedResponse.response}
                </div>

                <div className="space-y-3">
                  <Button
                    variant="primary"
                    fullWidth
                    onClick={() => handleCopyResponse(generatedResponse.response)}
                    icon={<Copy className="w-4 h-4" />}
                  >
                    응답 복사하기
                  </Button>

                  <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                    <p className="text-sm font-medium text-blue-500 mb-2">📋 다음 단계</p>
                    <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                      <li>위 버튼으로 응답 복사</li>
                      <li>네이버 플레이스 리뷰 페이지 접속</li>
                      <li>해당 리뷰에 응답으로 붙여넣기</li>
                      <li>필요시 내용 수정 후 등록</li>
                    </ol>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
                <p>리뷰 정보를 입력하고</p>
                <p>AI 응답 생성 버튼을 클릭하세요</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 템플릿 탭 */}
      {activeTab === 'templates' && (
        <div className="space-y-6">
          <div className="flex justify-end">
            <Button
              variant="primary"
              onClick={() => setNewTemplateModal(true)}
              icon={<Plus className="w-4 h-4" />}
            >
              새 템플릿
            </Button>
          </div>

          {templatesLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
          ) : (
            <div className="grid md:grid-cols-3 gap-6">
              {['positive', 'negative', 'neutral'].map((sentiment) => (
                <div key={sentiment} className="space-y-4">
                  <h3 className="font-bold flex items-center gap-2">
                    {sentimentIcons[sentiment as keyof typeof sentimentIcons]}
                    {sentimentLabels[sentiment as keyof typeof sentimentLabels]} 리뷰
                  </h3>

                  {templatesData?.templates?.[sentiment]?.map((template: Template) => (
                    <div
                      key={template.id}
                      className="bg-card rounded-lg border border-border p-4"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">{template.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {template.use_count}회 사용
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-3 mb-3">
                        {template.content}
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleUseTemplate(template)}
                          className="flex-1 bg-primary/10 text-primary hover:bg-primary/20"
                        >
                          사용
                        </Button>
                        <IconButton
                          icon={<Copy className="w-4 h-4" />}
                          onClick={() => handleCopyResponse(template.content)}
                          size="sm"
                          title="복사"
                        />
                        <IconButton
                          icon={<Trash2 className="w-4 h-4" />}
                          onClick={() => deleteTemplateMutation.mutate(template.id)}
                          size="sm"
                          title="삭제"
                          className="text-red-500 hover:bg-red-500/10"
                        />
                      </div>
                    </div>
                  ))}

                  {!templatesData?.templates?.[sentiment]?.length && (
                    <div className="text-center py-8 text-muted-foreground text-sm">
                      템플릿이 없습니다
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 히스토리 탭 */}
      {activeTab === 'history' && (
        <div className="space-y-4">
          {historyData?.history?.length > 0 ? (
            historyData.history.map((item: any) => (
              <div
                key={item.id}
                className="bg-card rounded-lg border border-border p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {sentimentIcons[item.sentiment as keyof typeof sentimentIcons]}
                    <span className="font-medium">{item.reviewer_name || '익명'}</span>
                    {item.rating && (
                      <span className="text-sm text-muted-foreground">
                        {item.rating}점
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleString('ko-KR')}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground mb-3 line-clamp-2">
                  원문: {item.review_content}
                </div>
                <div className="p-3 bg-muted/50 rounded text-sm">
                  {item.generated_response}
                </div>
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => handleCopyResponse(item.generated_response)}
                  icon={<Copy className="w-3 h-3" />}
                  className="mt-2"
                >
                  복사
                </Button>
              </div>
            ))
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <History className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>생성된 응답 히스토리가 없습니다</p>
            </div>
          )}
        </div>
      )}

      {/* 새 템플릿 모달 */}
      {newTemplateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg border border-border p-6 w-full max-w-md">
            <h3 className="font-bold text-lg mb-4">새 템플릿 추가</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">감정 유형</label>
                <select
                  value={newTemplate.sentiment}
                  onChange={(e) => setNewTemplate({ ...newTemplate, sentiment: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg bg-background"
                >
                  <option value="positive">긍정</option>
                  <option value="negative">부정</option>
                  <option value="neutral">중립</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">템플릿 이름</label>
                <input
                  type="text"
                  value={newTemplate.template_name}
                  onChange={(e) => setNewTemplate({ ...newTemplate, template_name: e.target.value })}
                  placeholder="예: 감사 인사"
                  className="w-full px-3 py-2 border border-border rounded-lg bg-background"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">템플릿 내용</label>
                <textarea
                  value={newTemplate.content}
                  onChange={(e) => setNewTemplate({ ...newTemplate, content: e.target.value })}
                  placeholder="{reviewer_name}을 사용하면 리뷰어 이름으로 치환됩니다"
                  className="w-full h-32 px-3 py-2 border border-border rounded-lg bg-background resize-none"
                />
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setNewTemplateModal(false)}
                  fullWidth
                >
                  취소
                </Button>
                <Button
                  variant="primary"
                  onClick={() => createTemplateMutation.mutate(newTemplate)}
                  disabled={!newTemplate.template_name || !newTemplate.content}
                  fullWidth
                >
                  추가
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
