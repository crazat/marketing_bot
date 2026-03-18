import { useState, useRef, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { pathfinderApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'

interface KeywordMemoEditorProps {
  keyword: string
  memo: string
  userTags: string[]
}

const PRESET_TAGS = ['중요', '우선순위', '작성완료', '진행중', '검토필요', '보류']

export default function KeywordMemoEditor({ keyword, memo: initialMemo, userTags: initialTags }: KeywordMemoEditorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [memo, setMemo] = useState(initialMemo || '')
  const [tags, setTags] = useState<string[]>(initialTags || [])
  const [newTag, setNewTag] = useState('')
  const popoverRef = useRef<HTMLDivElement>(null)
  const toast = useToast()
  const queryClient = useQueryClient()

  // 외부 클릭 감지
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const updateMutation = useMutation({
    mutationFn: () => pathfinderApi.updateKeyword(keyword, { memo, user_tags: tags }),
    onSuccess: () => {
      toast.success('저장되었습니다')
      queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
      setIsOpen(false)
    },
    onError: () => {
      toast.error('저장 실패')
    }
  })

  const handleAddTag = (tag: string) => {
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag])
      setNewTag('')
    }
  }

  const handleRemoveTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag))
  }

  const hasMemo = initialMemo && initialMemo.length > 0
  const hasTags = initialTags && initialTags.length > 0

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`p-1.5 rounded hover:bg-muted transition-colors ${
          hasMemo || hasTags ? 'text-primary' : 'text-muted-foreground'
        }`}
        title={hasMemo ? initialMemo : '메모/태그 추가'}
      >
        {hasMemo || hasTags ? '📝' : '➕'}
      </button>

      {/* 태그 미리보기 (있는 경우) */}
      {hasTags && !isOpen && (
        <div className="flex flex-wrap gap-1 mt-1">
          {initialTags.slice(0, 2).map(tag => (
            <span key={tag} className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded">
              {tag}
            </span>
          ))}
          {initialTags.length > 2 && (
            <span className="text-xs text-muted-foreground">+{initialTags.length - 2}</span>
          )}
        </div>
      )}

      {/* 편집 팝오버 */}
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-full mt-2 w-72 bg-card border border-border rounded-lg shadow-lg z-50 p-4"
        >
          <h4 className="font-semibold mb-3 text-sm">📝 메모 & 태그</h4>

          {/* 메모 입력 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-1 block">메모</label>
            <textarea
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="키워드 관련 메모..."
              className="w-full h-20 px-3 py-2 text-sm bg-background border border-border rounded-lg resize-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* 태그 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-1 block">태그</label>

            {/* 현재 태그 */}
            <div className="flex flex-wrap gap-1 mb-2 min-h-[24px]">
              {tags.map(tag => (
                <span
                  key={tag}
                  className="text-xs px-2 py-1 bg-primary/10 text-primary rounded-full flex items-center gap-1"
                >
                  {tag}
                  <button
                    onClick={() => handleRemoveTag(tag)}
                    className="hover:text-red-500"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>

            {/* 프리셋 태그 */}
            <div className="flex flex-wrap gap-1 mb-2">
              {PRESET_TAGS.filter(t => !tags.includes(t)).map(tag => (
                <button
                  key={tag}
                  onClick={() => handleAddTag(tag)}
                  className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded hover:bg-muted/80"
                >
                  + {tag}
                </button>
              ))}
            </div>

            {/* 커스텀 태그 입력 */}
            <div className="flex gap-1">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddTag(newTag)}
                placeholder="새 태그..."
                className="flex-1 px-2 py-1 text-xs bg-background border border-border rounded"
              />
              <Button
                variant="primary"
                size="xs"
                onClick={() => handleAddTag(newTag)}
                disabled={!newTag}
              >
                추가
              </Button>
            </div>
          </div>

          {/* 저장 버튼 */}
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsOpen(false)}
            >
              취소
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => updateMutation.mutate()}
              loading={updateMutation.isPending}
            >
              저장
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
