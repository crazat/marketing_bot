import { X } from 'lucide-react'
import { useEffect } from 'react'

interface ShortcutsOverlayProps {
  open: boolean
  onClose: () => void
}

const SHORTCUTS: Array<{
  section: string
  items: Array<{ keys: string[]; description: string }>
}> = [
  {
    section: '전역 네비게이션 (g-prefix)',
    items: [
      { keys: ['g', 'h'], description: '대시보드(Home)로 이동' },
      { keys: ['g', 'v'], description: 'Viral Hunter로 이동' },
      { keys: ['g', 'l'], description: 'Lead Manager로 이동' },
      { keys: ['g', 'p'], description: 'Pathfinder로 이동' },
      { keys: ['g', 'b'], description: 'Battle Intelligence로 이동' },
      { keys: ['g', 'c'], description: '경쟁사 분석으로 이동' },
      { keys: ['g', 'q'], description: 'Q&A Repository로 이동' },
      { keys: ['g', 'a'], description: '마케팅 분석으로 이동' },
      { keys: ['g', 's'], description: '설정으로 이동' },
    ],
  },
  {
    section: '작업 네비게이션',
    items: [
      { keys: ['J'], description: '다음 타겟으로 이동' },
      { keys: ['K'], description: '이전 타겟으로 이동' },
      { keys: ['Space', 'Esc'], description: '현재 타겟 접기' },
    ],
  },
  {
    section: '타겟 액션',
    items: [
      { keys: ['E', 'A'], description: '승인 (Approve) · 완료' },
      { keys: ['S'], description: '건너뛰기 (Skip) — 사유 없이 즉시' },
      { keys: ['Shift', 'S'], description: '스킵 + 사유 선택 (학습용)' },
      { keys: ['D'], description: '삭제 (Delete)' },
      { keys: ['G'], description: 'AI 댓글 생성 (Generate)' },
    ],
  },
  {
    section: '리스트 뷰',
    items: [
      { keys: ['Ctrl/Cmd', 'A'], description: '전체 선택 토글' },
      { keys: ['Ctrl/Cmd', 'D'], description: '선택 해제' },
      { keys: ['A / S / D'], description: '선택된 항목 일괄 처리' },
    ],
  },
  {
    section: '전역',
    items: [
      { keys: ['Ctrl/Cmd', 'K'], description: '명령 팔레트 열기' },
      { keys: ['?'], description: '이 단축키 도움말 토글' },
    ],
  },
  {
    section: '토스트 액션',
    items: [
      { keys: ['되돌리기'], description: '승인/스킵 직후 5초 내 Undo (토스트 내 버튼)' },
    ],
  },
]

export default function ShortcutsOverlay({ open, onClose }: ShortcutsOverlayProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-xl p-6 max-w-lg w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">⌨️ 키보드 단축키</h2>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5">
          {SHORTCUTS.map((section) => (
            <div key={section.section}>
              <h3 className="text-sm font-medium text-muted-foreground mb-2">{section.section}</h3>
              <div className="space-y-1.5">
                {section.items.map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <span>{item.description}</span>
                    <div className="flex items-center gap-1">
                      {item.keys.map((k, i) => (
                        <kbd
                          key={i}
                          className="px-2 py-1 text-xs font-mono border border-border rounded bg-muted/40"
                        >
                          {k}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-muted-foreground mt-5 border-t border-border pt-3">
          입력창에 포커스가 있을 때는 단축키가 작동하지 않습니다.
        </p>
      </div>
    </div>
  )
}
