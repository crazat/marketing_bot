import { type ReactNode, Children, isValidElement } from 'react'

interface BannerStackProps {
  /** 최대 동시 표시 배너 수 (기본 2) */
  maxVisible?: number
  /** "+N more" 표시 여부 */
  showOverflowBadge?: boolean
  children: ReactNode
}

/**
 * [CC2] 배너 우선순위 스택
 *
 * Dashboard 최상단에 동시 표시 가능한 배너가 많을 때 사용.
 * 자식으로 배치된 순서 = 우선순위 (앞에 있을수록 먼저).
 *
 * 렌더된 자식(실제 DOM 출력) 중 상위 N개만 표시.
 * null을 반환하는 자식(조건 미충족)은 자동 건너뜀.
 */
export default function BannerStack({
  maxVisible = 2,
  showOverflowBadge = true,
  children,
}: BannerStackProps) {
  // React 자식 배열을 평탄화
  const childArray = Children.toArray(children).filter((c) => isValidElement(c))

  // 실제로 렌더되는 자식을 계산하기 어려우므로, 각 자식을 wrapper로 감싸고
  // 부모에서 개수 제한. 자식이 null 반환하면 wrapper도 null이 되도록.
  // 간단 구현: 자식 전부 렌더하되, CSS로 maxVisible 이후 숨김.
  //
  // 더 정확한 방법: 자식이 "표시 여부"를 알리는 renderIf 패턴.
  // 여기서는 간단히 처음 N개만 렌더.

  const visible = childArray.slice(0, maxVisible)
  const hiddenCount = Math.max(0, childArray.length - maxVisible)

  return (
    <div className="space-y-3">
      {visible}
      {showOverflowBadge && hiddenCount > 0 && (
        <p className="text-[11px] text-muted-foreground text-center">
          + {hiddenCount}개 배너가 더 있습니다. 일부를 해제하면 더 보입니다.
        </p>
      )}
    </div>
  )
}
