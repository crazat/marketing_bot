/**
 * 연동 상태 탭 컴포넌트
 * Instagram Graph API 및 기타 API 연동 상태
 */

import { useQuery } from '@tanstack/react-query'
import { instagramApi } from '@/services/api'

interface InstagramTokenStatus {
  configured: boolean
  status: 'valid' | 'warning' | 'expiring_soon' | 'expired' | 'not_configured' | 'error'
  message: string
  days_until_expiry?: number | null
  token_expiry?: string
  required_keys?: string[]
}

export default function IntegrationsTab() {
  // Instagram 토큰 상태 조회
  const { data: instagramTokenStatus, isLoading: instagramLoading } = useQuery<InstagramTokenStatus>({
    queryKey: ['instagram-token-status'],
    queryFn: () => instagramApi.getTokenStatus().catch(() => ({
      configured: false,
      status: 'error' as const,
      message: 'API 연결 실패'
    })),
    refetchInterval: 60000,
    retry: 1,
  })

  return (
    <div className="space-y-6">
      {/* Instagram API 상태 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📸 Instagram Graph API</h3>

        {instagramLoading ? (
          <div className="animate-pulse">
            <div className="h-20 bg-muted rounded-lg" />
          </div>
        ) : instagramTokenStatus ? (
          <div className="space-y-4">
            {/* 상태 표시 */}
            <div className={`p-4 rounded-lg border ${
              instagramTokenStatus.status === 'valid' ? 'bg-green-500/10 border-green-500/30' :
              instagramTokenStatus.status === 'warning' ? 'bg-yellow-500/10 border-yellow-500/30' :
              instagramTokenStatus.status === 'expiring_soon' ? 'bg-orange-500/10 border-orange-500/30' :
              instagramTokenStatus.status === 'expired' ? 'bg-red-500/10 border-red-500/30' :
              'bg-muted border-border'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">
                    {instagramTokenStatus.status === 'valid' ? '✅' :
                     instagramTokenStatus.status === 'warning' ? '⚠️' :
                     instagramTokenStatus.status === 'expiring_soon' ? '🔶' :
                     instagramTokenStatus.status === 'expired' ? '❌' :
                     instagramTokenStatus.status === 'not_configured' ? '⚙️' :
                     '❓'}
                  </span>
                  <div>
                    <p className="font-medium">
                      {instagramTokenStatus.configured ? '연동됨' : '미설정'}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {instagramTokenStatus.message}
                    </p>
                  </div>
                </div>
                {instagramTokenStatus.days_until_expiry !== null && instagramTokenStatus.days_until_expiry !== undefined && (
                  <div className="text-right">
                    <p className={`text-2xl font-bold ${
                      instagramTokenStatus.days_until_expiry < 7 ? 'text-red-500' :
                      instagramTokenStatus.days_until_expiry < 14 ? 'text-yellow-500' :
                      'text-green-500'
                    }`}>
                      D-{instagramTokenStatus.days_until_expiry}
                    </p>
                    <p className="text-xs text-muted-foreground">만료까지</p>
                  </div>
                )}
              </div>
            </div>

            {/* 토큰 정보 */}
            {instagramTokenStatus.token_expiry && (
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-muted-foreground">토큰 만료일</p>
                  <p className="font-medium">
                    {new Date(instagramTokenStatus.token_expiry).toLocaleDateString('ko-KR', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric'
                    })}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-muted-foreground">토큰 유효 기간</p>
                  <p className="font-medium">60일 (Facebook 정책)</p>
                </div>
              </div>
            )}

            {/* 필요 설정 키 (미설정 시) */}
            {instagramTokenStatus.required_keys && (
              <div className="p-4 bg-muted/50 rounded-lg">
                <p className="text-sm font-medium mb-2">필요한 설정 키 (secrets.json)</p>
                <ul className="space-y-1 text-xs text-muted-foreground font-mono">
                  {instagramTokenStatus.required_keys.map((key: string) => (
                    <li key={key}>• {key}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* 갱신 안내 */}
            {(instagramTokenStatus.status === 'expiring_soon' || instagramTokenStatus.status === 'expired') && (
              <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                <p className="text-sm font-medium text-blue-500 mb-2">토큰 갱신 방법</p>
                <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                  <li>Facebook Developer Console 접속</li>
                  <li>Instagram Graph API 앱 선택</li>
                  <li>Tools → Graph API Explorer에서 토큰 갱신</li>
                  <li>secrets.json의 INSTAGRAM_ACCESS_TOKEN 업데이트</li>
                  <li>INSTAGRAM_TOKEN_EXPIRY 날짜 업데이트</li>
                </ol>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <p>Instagram API 상태를 불러올 수 없습니다.</p>
          </div>
        )}
      </div>

      {/* 기타 API 상태 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">🔌 기타 API 연동</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-muted/50 rounded-lg flex items-center gap-3">
            <span className="text-2xl">✅</span>
            <div>
              <p className="font-medium">Gemini AI</p>
              <p className="text-xs text-muted-foreground">config.json에서 설정</p>
            </div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg flex items-center gap-3">
            <span className="text-2xl">✅</span>
            <div>
              <p className="font-medium">Naver API</p>
              <p className="text-xs text-muted-foreground">config.json에서 설정</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
