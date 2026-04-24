/**
 * Viral Hunter View 컴포넌트 배럴
 * [D6] React.memo 적용 — scan 폴링 등 상위 재렌더에도 props 미변경 시 리렌더 회피
 */
import { memo } from 'react'
import { HomeView as HomeViewRaw } from './HomeView'
import { WorkView as WorkViewRaw } from './WorkView'
import { ListView as ListViewRaw } from './ListView'
import { CompletionView as CompletionViewRaw } from './CompletionView'

export const HomeView = memo(HomeViewRaw)
export const WorkView = memo(WorkViewRaw)
export const ListView = memo(ListViewRaw)
export const CompletionView = memo(CompletionViewRaw)
