/* ════════════════════════════════════════════════════════════════════════
   [RECOVER OS] 엔티티 → 라인 아이콘 공용 헬퍼 (이모지 대체)
   플랫폼 / 리드 등급 / 상태 매핑. leads·viral·pathfinder 컴포넌트 공용.
   ════════════════════════════════════════════════════════════════════════ */
import type { ReactNode } from 'react'
import {
  Youtube, Music, Instagram, Carrot, Star, Coffee, FileText, Folder, Globe,
  BarChart3, Clock, Phone, MessageSquare, CheckCircle, XCircle,
  Flame, Thermometer, ThermometerSun, Snowflake,
} from 'lucide-react'

const ic = (cls: string) => ({ className: cls, strokeWidth: 1.7 as const })

export function platformIcon(p: string, cls = 'w-[18px] h-[18px]'): ReactNode {
  const key = (p || '').toLowerCase()
  const m: Record<string, ReactNode> = {
    youtube: <Youtube {...ic(cls)} />,
    tiktok: <Music {...ic(cls)} />,
    naver: <Globe {...ic(cls)} />,
    cafe: <Coffee {...ic(cls)} />,
    instagram: <Instagram {...ic(cls)} />,
    carrot: <Carrot {...ic(cls)} />,
    karrot: <Carrot {...ic(cls)} />,
    influencer: <Star {...ic(cls)} />,
    blog: <FileText {...ic(cls)} />,
    all: <BarChart3 {...ic(cls)} />,
    total: <BarChart3 {...ic(cls)} />,
    other: <Folder {...ic(cls)} />,
  }
  return m[key] ?? <Folder {...ic(cls)} />
}

export function gradeIcon(g: string, cls = 'w-[18px] h-[18px]'): ReactNode {
  const m: Record<string, ReactNode> = {
    hot: <Flame {...ic(cls)} />,
    warm: <ThermometerSun {...ic(cls)} />,
    cool: <Thermometer {...ic(cls)} />,
    cold: <Snowflake {...ic(cls)} />,
  }
  return m[(g || '').toLowerCase()] ?? <Thermometer {...ic(cls)} />
}

export function statusIcon(s: string, cls = 'w-[18px] h-[18px]'): ReactNode {
  const m: Record<string, ReactNode> = {
    pending: <Clock {...ic(cls)} />,
    contacted: <Phone {...ic(cls)} />,
    replied: <MessageSquare {...ic(cls)} />,
    converted: <CheckCircle {...ic(cls)} />,
    rejected: <XCircle {...ic(cls)} />,
  }
  return m[(s || '').toLowerCase()] ?? <Clock {...ic(cls)} />
}
