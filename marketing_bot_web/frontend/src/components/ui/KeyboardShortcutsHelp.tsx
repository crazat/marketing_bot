/**
 * Keyboard Shortcuts Help Dialog
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 1.5] 키보드 단축키 도움말 모달
 */

interface KeyboardShortcutsHelpProps {
  isOpen: boolean
  onClose: () => void
  shortcuts: Array<{ key: string; description: string }>
}

export default function KeyboardShortcutsHelp({
  isOpen,
  onClose,
  shortcuts
}: KeyboardShortcutsHelpProps) {
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-lg shadow-xl max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <span>⌨️</span> 키보드 단축키
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-2">
          {shortcuts.map((shortcut, index) => (
            <div
              key={index}
              className="flex items-center justify-between py-2 border-b border-border last:border-b-0"
            >
              <span className="text-muted-foreground">{shortcut.description}</span>
              <kbd className="px-2 py-1 bg-muted rounded text-sm font-mono">
                {shortcut.key}
              </kbd>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-border text-center text-sm text-muted-foreground">
          <kbd className="px-2 py-1 bg-muted rounded text-xs font-mono">Shift</kbd>
          {' + '}
          <kbd className="px-2 py-1 bg-muted rounded text-xs font-mono">?</kbd>
          {' 로 언제든 이 도움말을 볼 수 있습니다'}
        </div>
      </div>
    </div>
  )
}
