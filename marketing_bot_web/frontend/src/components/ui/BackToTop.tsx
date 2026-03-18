/**
 * Back to Top 버튼 컴포넌트
 * 스크롤 위치가 500px 이상일 때 표시
 */
import { useState, useEffect } from 'react'
import { ArrowUp } from 'lucide-react'
import { IconButton } from '@/components/ui/Button'

interface BackToTopProps {
  threshold?: number
  className?: string
}

export default function BackToTop({ threshold = 500, className = '' }: BackToTopProps) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setIsVisible(window.scrollY > threshold)
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll() // 초기 상태 확인

    return () => window.removeEventListener('scroll', handleScroll)
  }, [threshold])

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    })
  }

  if (!isVisible) return null

  return (
    <IconButton
      icon={<ArrowUp className="w-5 h-5" />}
      onClick={scrollToTop}
      title="맨 위로"
      className={`
        fixed bottom-6 right-6 z-40
        p-3 rounded-full shadow-lg
        bg-primary text-primary-foreground
        hover:bg-primary/90 hover:scale-110
        transition-all duration-300 ease-out
        ${className}
      `}
    />
  )
}
