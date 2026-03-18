/**
 * [Phase 6.0] 키워드 팝오버 메뉴 컴포넌트
 * 키워드 클릭 시 컨텍스트 액션 메뉴 표시
 */

import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { TrendingUp, Users, FileText, Copy, ExternalLink, X, Target } from 'lucide-react'
import { useToast } from './Toast'
import { battleApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

interface KeywordPopoverProps {
  keyword: string
  grade?: 'S' | 'A' | 'B' | 'C' | string
  searchVolume?: number
  children: React.ReactNode
  className?: string
}

export default function KeywordPopover({
  keyword,
  grade,
  searchVolume,
  children,
  className = '',
}: KeywordPopoverProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const triggerRef = useRef<HTMLDivElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const toast = useToast()
  const queryClient = useQueryClient()

  // [Phase 8.0] 순위 추적 등록 mutation
  const addTrackingMutation = useMutation({
    mutationFn: (kw: string) => battleApi.addRankingKeyword(kw, 10, '한의원'),
    onSuccess: () => {
      toast.success(`"${keyword}" 순위 추적이 시작되었습니다`)
      queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
      queryClient.invalidateQueries({ queryKey: ['ranking-keywords-pipeline'] })
      setIsOpen(false)
    },
    onError: (error: any) => {
      if (error?.message?.includes('already exists') || error?.detail?.includes('already exists')) {
        toast.info('이미 순위 추적 중인 키워드입니다')
      } else {
        toast.error('순위 추적 등록 실패: ' + (error?.message || '알 수 없는 오류'))
      }
    },
  })

  // 클릭 외부 감지
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // 팝오버 위치 계산
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const viewportWidth = window.innerWidth
      const popoverWidth = 280

      // 오른쪽 공간이 부족하면 왼쪽에 표시
      let left = rect.left
      if (rect.left + popoverWidth > viewportWidth) {
        left = rect.right - popoverWidth
      }

      setPosition({
        top: rect.bottom + window.scrollY + 8,
        left: left + window.scrollX,
      })
    }
    setIsOpen(!isOpen)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(keyword)
    toast.success('키워드가 복사되었습니다')
    setIsOpen(false)
  }

  const handleViewRanking = () => {
    navigate(`/battle?keyword=${encodeURIComponent(keyword)}`)
    setIsOpen(false)
  }

  const handleViewLeads = () => {
    navigate(`/leads?keyword=${encodeURIComponent(keyword)}`)
    setIsOpen(false)
  }

  const handleCreateContent = () => {
    navigate(`/viral?keyword=${encodeURIComponent(keyword)}`)
    setIsOpen(false)
  }

  const handleSearchNaver = () => {
    window.open(`https://search.naver.com/search.naver?query=${encodeURIComponent(keyword)}`, '_blank')
    setIsOpen(false)
  }

  // [Phase 8.0] 순위 추적 시작
  const handleStartTracking = () => {
    addTrackingMutation.mutate(keyword)
  }

  const gradeColors: Record<string, string> = {
    S: 'bg-purple-500',
    A: 'bg-blue-500',
    B: 'bg-green-500',
    C: 'bg-gray-500',
  }

  return (
    <>
      <div
        ref={triggerRef}
        onClick={handleClick}
        className={`cursor-pointer inline-flex items-center gap-1 hover:opacity-80 transition-opacity ${className}`}
      >
        {children}
      </div>

      {isOpen && (
        <div
          ref={popoverRef}
          className="fixed z-50 bg-card border border-border rounded-lg shadow-lg p-3 w-[280px]"
          style={{ top: position.top, left: position.left }}
        >
          {/* 헤더 */}
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
            <div className="flex items-center gap-2">
              {grade && (
                <span className={`text-xs px-1.5 py-0.5 rounded text-white font-bold ${gradeColors[grade] || 'bg-gray-500'}`}>
                  {grade}
                </span>
              )}
              <span className="font-semibold text-sm truncate max-w-[180px]">{keyword}</span>
            </div>
            <IconButton
              icon={<X className="w-3 h-3" />}
              onClick={() => setIsOpen(false)}
              size="sm"
              title="닫기"
            />
          </div>

          {/* 검색량 표시 */}
          {searchVolume !== undefined && (
            <div className="mb-3 text-xs text-muted-foreground">
              월간 검색량: <span className="font-medium text-foreground">{searchVolume.toLocaleString()}</span>
            </div>
          )}

          {/* 액션 버튼들 */}
          <div className="space-y-1">
            {/* [Phase 8.0] 순위 추적 시작 - S/A 등급에 강조 */}
            <Button
              variant={grade === 'S' || grade === 'A' ? 'outline' : 'ghost'}
              fullWidth
              onClick={handleStartTracking}
              loading={addTrackingMutation.isPending}
              icon={<Target className="w-4 h-4 text-primary" />}
              className={`justify-start ${
                grade === 'S' || grade === 'A' ? 'text-primary font-medium' : ''
              }`}
            >
              <span className="flex-1 text-left">순위 추적 시작</span>
              {(grade === 'S' || grade === 'A') && (
                <span className="text-xs bg-primary/20 px-1.5 py-0.5 rounded">권장</span>
              )}
            </Button>

            <Button
              variant="ghost"
              fullWidth
              onClick={handleViewRanking}
              icon={<TrendingUp className="w-4 h-4 text-blue-500" />}
              className="justify-start"
            >
              순위 히스토리 보기
            </Button>

            <Button
              variant="ghost"
              fullWidth
              onClick={handleViewLeads}
              icon={<Users className="w-4 h-4 text-green-500" />}
              className="justify-start"
            >
              관련 리드 검색
            </Button>

            <Button
              variant="ghost"
              fullWidth
              onClick={handleCreateContent}
              icon={<FileText className="w-4 h-4 text-purple-500" />}
              className="justify-start"
            >
              콘텐츠 아이디어
            </Button>

            <div className="border-t border-border my-2" />

            <Button
              variant="ghost"
              fullWidth
              onClick={handleCopy}
              icon={<Copy className="w-4 h-4 text-muted-foreground" />}
              className="justify-start"
            >
              클립보드 복사
            </Button>

            <Button
              variant="ghost"
              fullWidth
              onClick={handleSearchNaver}
              icon={<ExternalLink className="w-4 h-4 text-muted-foreground" />}
              className="justify-start"
            >
              네이버 검색
            </Button>
          </div>
        </div>
      )}
    </>
  )
}
