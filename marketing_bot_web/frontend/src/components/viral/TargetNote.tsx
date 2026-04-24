import { useEffect, useState } from 'react'
import { StickyNote, Check } from 'lucide-react'
import { useTargetNote } from '@/hooks/useTargetNotes'
import { formatRelative } from '@/utils/format'

interface TargetNoteProps {
  targetId: string
}

/**
 * [BB7] 타겟 개인 메모 — WorkView expanded에 내장
 *
 * 사용자가 이 타겟에 대해 남기고 싶은 개인적 맥락/결정 근거 기록.
 * 2초 디바운스 자동 저장, "저장됨" 피드백.
 */
export default function TargetNote({ targetId }: TargetNoteProps) {
  const { note, updatedAt, saveNote } = useTargetNote(targetId)
  const [draft, setDraft] = useState(note)
  const [justSaved, setJustSaved] = useState(false)

  useEffect(() => {
    setDraft(note)
  }, [note])

  useEffect(() => {
    if (draft === note) return
    const timer = setTimeout(() => {
      saveNote(draft)
      setJustSaved(true)
      const t = setTimeout(() => setJustSaved(false), 2000)
      return () => clearTimeout(t)
    }, 1500)
    return () => clearTimeout(timer)
  }, [draft, note, saveNote])

  return (
    <div className="border border-border bg-muted/20 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="caps text-muted-foreground flex items-center gap-1.5">
          <StickyNote className="w-3 h-3" aria-hidden />
          <span>내 메모 · Personal Note</span>
        </div>
        <div className="text-[10px] text-muted-foreground flex items-center gap-2">
          {justSaved && (
            <span className="inline-flex items-center gap-1 text-emerald-600">
              <Check className="w-3 h-3" aria-hidden />
              저장됨
            </span>
          )}
          {updatedAt && !justSaved && <span>{formatRelative(updatedAt)} 수정</span>}
        </div>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="이 타겟에 대한 나만의 메모 — 처리 이유, 후속 액션, 주의점 등. 자동 저장됩니다."
        className="w-full min-h-[60px] bg-background border border-border p-2 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary"
        maxLength={500}
      />
    </div>
  )
}
