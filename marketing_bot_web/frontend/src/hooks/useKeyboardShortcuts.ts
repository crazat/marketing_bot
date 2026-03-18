/**
 * Keyboard Shortcuts Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * 키보드 단축키 시스템
 * - Ctrl+1~6: 페이지 이동
 * - Ctrl+R: 새로고침
 * - Ctrl+K: 명령 팔레트 (Layout.tsx에서 처리)
 * - Shift+?: 단축키 도움말
 * - Escape: 모달 닫기
 */

import { useEffect, useCallback, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

export function useKeyboardShortcuts() {
  const navigate = useNavigate()
  const location = useLocation()
  const [showHelp, setShowHelp] = useState(false)

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // 입력 필드에서는 단축키 비활성화
    const target = event.target as HTMLElement
    if (
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable
    ) {
      return
    }

    // Ctrl + 숫자키 페이지 이동
    if (event.ctrlKey && !event.shiftKey && !event.altKey) {
      switch (event.key) {
        case '1':
          event.preventDefault()
          navigate('/')
          break
        case '2':
          event.preventDefault()
          navigate('/pathfinder')
          break
        case '3':
          event.preventDefault()
          navigate('/battle')
          break
        case '4':
          event.preventDefault()
          navigate('/viral')
          break
        case '5':
          event.preventDefault()
          navigate('/leads')
          break
        case '6':
          event.preventDefault()
          navigate('/competitors')
          break
        case 'r':
        case 'R':
          // 새로고침 (브라우저 기본 동작 허용)
          break
        case 'k':
        case 'K':
          // CommandPalette는 Layout.tsx에서 처리됨
          break
      }
    }

    // ? 키로 도움말 토글
    if (event.key === '?' && event.shiftKey) {
      event.preventDefault()
      setShowHelp(prev => !prev)
    }

    // Escape로 도움말/모달 닫기
    if (event.key === 'Escape') {
      setShowHelp(false)
    }
  }, [navigate])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [handleKeyDown])

  // 현재 페이지에 해당하는 단축키 번호 반환
  const getCurrentShortcut = useCallback(() => {
    const pathMap: Record<string, string> = {
      '/': '1',
      '/pathfinder': '2',
      '/battle': '3',
      '/viral': '4',
      '/leads': '5',
      '/competitors': '6',
    }
    return pathMap[location.pathname] || null
  }, [location.pathname])

  return {
    showHelp,
    setShowHelp,
    getCurrentShortcut,
    shortcuts: [
      { key: 'Ctrl+1', description: '대시보드' },
      { key: 'Ctrl+2', description: 'Pathfinder' },
      { key: 'Ctrl+3', description: 'Battle Intelligence' },
      { key: 'Ctrl+4', description: 'Viral Hunter' },
      { key: 'Ctrl+5', description: 'Lead Manager' },
      { key: 'Ctrl+6', description: 'Competitor Analysis' },
      { key: 'Ctrl+R', description: '새로고침' },
      { key: 'Shift+?', description: '단축키 도움말' },
    ]
  }
}

export default useKeyboardShortcuts
