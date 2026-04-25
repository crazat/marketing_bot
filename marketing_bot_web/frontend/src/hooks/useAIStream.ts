/**
 * useAIStream — SSE-backed Korean AI generation hook.
 *
 * Wraps EventSource to stream Gemini output token-by-token.
 * Handles auto-cleanup, abort, error states.
 *
 * Usage:
 *   const { text, isStreaming, error, start, stop } = useAIStream();
 *   <button onClick={() => start({ prompt: "청주 한의원 추천" })}>생성</button>
 *   <p>{text}{isStreaming && '...'}</p>
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export interface AIStreamOptions {
  prompt: string
  systemPrompt?: string
  temperature?: number
  maxTokens?: number
}

export interface AIStreamState {
  text: string
  isStreaming: boolean
  error: string | null
  start: (opts: AIStreamOptions) => void
  stop: () => void
  reset: () => void
}

const API_BASE = '/api/agent/stream'

function buildUrl(opts: AIStreamOptions): string {
  const params = new URLSearchParams()
  params.set('prompt', opts.prompt)
  if (opts.systemPrompt) params.set('system_prompt', opts.systemPrompt)
  if (opts.temperature !== undefined) params.set('temperature', String(opts.temperature))
  if (opts.maxTokens !== undefined) params.set('max_tokens', String(opts.maxTokens))
  return `${API_BASE}?${params.toString()}`
}

export function useAIStream(): AIStreamState {
  const [text, setText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sourceRef = useRef<EventSource | null>(null)

  const stop = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setIsStreaming(false)
  }, [])

  const reset = useCallback(() => {
    stop()
    setText('')
    setError(null)
  }, [stop])

  const start = useCallback((opts: AIStreamOptions) => {
    reset()
    setIsStreaming(true)
    setError(null)

    const es = new EventSource(buildUrl(opts))
    sourceRef.current = es

    es.onmessage = (ev) => {
      // 백엔드에서 \n을 \\n으로 escape 했으므로 복원
      const chunk = ev.data.replace(/\\n/g, '\n')
      setText((prev) => prev + chunk)
    }
    es.addEventListener('done', () => {
      setIsStreaming(false)
      es.close()
      sourceRef.current = null
    })
    es.addEventListener('error', (ev: Event) => {
      const data = (ev as MessageEvent).data
      setError(typeof data === 'string' && data ? data : 'stream error')
      setIsStreaming(false)
      es.close()
      sourceRef.current = null
    })
  }, [reset])

  // unmount cleanup
  useEffect(() => {
    return () => {
      if (sourceRef.current) {
        sourceRef.current.close()
        sourceRef.current = null
      }
    }
  }, [])

  return { text, isStreaming, error, start, stop, reset }
}
