import { Search, Command } from 'lucide-react'

interface GlobalSearchBarProps {
  onOpen: () => void
}

/**
 * [Y3] 전역 헤더 검색 바 — Command Palette 진입 유도
 *
 * 항상 보이는 검색 바 형태로, 클릭 시 Command Palette 열림.
 * 마우스 사용자의 발견성 보장.
 */
export default function GlobalSearchBar({ onOpen }: GlobalSearchBarProps) {
  return (
    <button
      onClick={onOpen}
      type="button"
      aria-label="명령 팔레트 열기 — 키워드, 리드, 페이지 검색 (Ctrl+K)"
      className="group w-full max-w-md mb-5 flex items-center gap-2.5 px-3.5 py-2 bg-card border border-border hover:border-primary/50 hover:bg-muted/30 transition-all text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <Search className="w-4 h-4 text-muted-foreground shrink-0 group-hover:text-primary transition-colors" aria-hidden />
      <span className="flex-1 text-sm text-muted-foreground truncate">
        키워드 · 리드 · 타겟 · 페이지 검색…
      </span>
      <span className="hidden sm:inline-flex items-center gap-0.5 text-[10px] text-muted-foreground/70">
        <kbd className="px-1 py-0.5 border border-border rounded bg-muted/40 font-mono">
          <Command className="inline w-2.5 h-2.5 -mt-0.5" aria-hidden />
        </kbd>
        <kbd className="px-1 py-0.5 border border-border rounded bg-muted/40 font-mono">K</kbd>
      </span>
    </button>
  )
}
