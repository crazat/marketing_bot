import { Link } from 'react-router-dom'
import { Home, Search } from 'lucide-react'

/**
 * [M6] 404 Not Found 페이지.
 * 존재하지 않는 경로 접근 시 사용자에게 명확한 안내 제공.
 */
export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
      <div className="text-7xl font-bold text-muted-foreground mb-3">404</div>
      <h1 className="text-2xl font-semibold mb-2">페이지를 찾을 수 없습니다</h1>
      <p className="text-muted-foreground mb-6 max-w-md">
        요청하신 경로가 존재하지 않습니다. URL을 다시 확인하거나 대시보드로 돌아가 주세요.
      </p>
      <div className="flex gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded bg-primary text-primary-foreground hover:bg-primary/90"
        >
          <Home className="h-4 w-4" />
          대시보드
        </Link>
        <Link
          to="/viral-hunter"
          className="inline-flex items-center gap-2 px-4 py-2 rounded border border-border hover:bg-muted"
        >
          <Search className="h-4 w-4" />
          바이럴 헌터
        </Link>
      </div>
    </div>
  )
}
