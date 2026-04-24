import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-target-notes-v1'

type NotesMap = Record<string, { text: string; updatedAt: number }>

function loadAll(): NotesMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveAll(all: NotesMap) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // ignore
  }
}

/**
 * [BB7] 타겟별 개인 메모 — localStorage scope
 *
 * target_id별 개인 메모. 다음 방문 시 복원.
 * 왜 이 타겟을 이렇게 처리했는지 사용자 자신에게 남기는 흔적.
 */
export function useTargetNote(targetId: string | null) {
  const [note, setNote] = useState('')
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)

  useEffect(() => {
    if (!targetId) {
      setNote('')
      setUpdatedAt(null)
      return
    }
    const all = loadAll()
    const entry = all[targetId]
    setNote(entry?.text ?? '')
    setUpdatedAt(entry?.updatedAt ?? null)
  }, [targetId])

  const saveNote = useCallback(
    (text: string) => {
      if (!targetId) return
      const all = loadAll()
      const trimmed = text.trim()
      if (!trimmed) {
        delete all[targetId]
      } else {
        all[targetId] = { text: trimmed, updatedAt: Date.now() }
      }
      saveAll(all)
      setNote(trimmed)
      setUpdatedAt(Date.now())
    },
    [targetId],
  )

  return { note, updatedAt, setNote, saveNote }
}
