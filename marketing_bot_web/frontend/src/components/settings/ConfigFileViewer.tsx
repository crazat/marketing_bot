/**
 * 설정 파일 뷰어 컴포넌트
 * [Phase 4] keywords.json, config.json, schedule.json 파일 내용 확인
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { configApi } from '@/services/api'

export default function ConfigFileViewer() {
  const [selectedFile, setSelectedFile] = useState<'keywords' | 'config' | 'schedule'>('keywords')

  const { data: fileData, isLoading } = useQuery({
    queryKey: ['config-file', selectedFile],
    queryFn: () => configApi.viewConfigFile(selectedFile),
    retry: 1,
  })

  return (
    <div className="bg-card border border-border rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">📄 설정 파일 뷰어</h3>
        <select
          value={selectedFile}
          onChange={(e) => setSelectedFile(e.target.value as 'keywords' | 'config' | 'schedule')}
          className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="keywords">keywords.json</option>
          <option value="config">config.json (민감 정보 마스킹)</option>
          <option value="schedule">schedule.json</option>
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          로딩 중...
        </div>
      ) : fileData ? (
        <div className="space-y-2">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>크기: {(fileData.metadata?.size_bytes / 1024).toFixed(1)} KB</span>
            <span>수정: {new Date(fileData.metadata?.modified).toLocaleString('ko-KR')}</span>
          </div>
          <pre className="bg-background border border-border rounded-lg p-4 overflow-auto max-h-96 text-xs">
            {JSON.stringify(fileData.content, null, 2)}
          </pre>
          <p className="text-xs text-muted-foreground">
            💡 읽기 전용입니다. 파일을 수정하려면 VS Code나 메모장으로 직접 편집하세요.
          </p>
        </div>
      ) : (
        <div className="text-center py-8 text-red-500">
          파일을 불러올 수 없습니다.
        </div>
      )}
    </div>
  )
}
