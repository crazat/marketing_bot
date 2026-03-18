/**
 * 키워드 관리 탭 컴포넌트
 * keywords.json 편집 - 네이버 플레이스 / 블로그 SEO 키워드 관리
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configApi } from '@/services/api'
import type { KeywordsData } from '@/services/api/base'
import Button, { IconButton } from '@/components/ui/Button'
import { ConfirmModal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import {
  Key,
  Plus,
  ArrowRightLeft,
  Trash2,
} from 'lucide-react'

export default function KeywordsTab() {
  const queryClient = useQueryClient()
  const toast = useToast()

  // 키워드 관련 상태
  const [newKeyword, setNewKeyword] = useState('')
  const [newKeywordCategory, setNewKeywordCategory] = useState<'naver_place' | 'blog_seo'>('naver_place')
  const [keywordToDelete, setKeywordToDelete] = useState<{ keyword: string; category: 'naver_place' | 'blog_seo' } | null>(null)
  const [keywordToMove, setKeywordToMove] = useState<{ keyword: string; from: 'naver_place' | 'blog_seo' } | null>(null)

  // 키워드 조회
  const { data: keywordsData, isLoading: keywordsLoading } = useQuery({
    queryKey: ['keywords-config'],
    queryFn: () => configApi.getKeywords().catch((): KeywordsData => ({ naver_place: [], blog_seo: [] })),
    retry: 1,
  })

  // 키워드 추가 mutation
  const addKeywordMutation = useMutation({
    mutationFn: ({ keyword, category }: { keyword: string; category: 'naver_place' | 'blog_seo' }) =>
      configApi.addKeyword(keyword, category),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['keywords-config'] })
      setNewKeyword('')
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 키워드 삭제 mutation
  const deleteKeywordMutation = useMutation({
    mutationFn: ({ keyword, category }: { keyword: string; category: 'naver_place' | 'blog_seo' }) =>
      configApi.deleteKeyword(keyword, category),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['keywords-config'] })
      setKeywordToDelete(null)
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 키워드 이동 mutation
  const moveKeywordMutation = useMutation({
    mutationFn: ({ keyword, from, to }: { keyword: string; from: 'naver_place' | 'blog_seo'; to: 'naver_place' | 'blog_seo' }) =>
      configApi.moveKeyword(keyword, from, to),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['keywords-config'] })
      setKeywordToMove(null)
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  return (
    <>
      {/* 키워드 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={keywordToDelete !== null}
        onClose={() => setKeywordToDelete(null)}
        onConfirm={() => keywordToDelete && deleteKeywordMutation.mutate(keywordToDelete)}
        title="키워드 삭제"
        message={`'${keywordToDelete?.keyword}'를 삭제하시겠습니까?`}
        confirmText="삭제"
        cancelText="취소"
        variant="danger"
        loading={deleteKeywordMutation.isPending}
      />

      {/* 키워드 이동 확인 모달 */}
      <ConfirmModal
        isOpen={keywordToMove !== null}
        onClose={() => setKeywordToMove(null)}
        onConfirm={() => {
          if (keywordToMove) {
            const to = keywordToMove.from === 'naver_place' ? 'blog_seo' : 'naver_place'
            moveKeywordMutation.mutate({
              keyword: keywordToMove.keyword,
              from: keywordToMove.from,
              to
            })
          }
        }}
        title="키워드 이동"
        message={`'${keywordToMove?.keyword}'를 ${keywordToMove?.from === 'naver_place' ? '블로그 SEO' : '네이버 플레이스'}로 이동하시겠습니까?`}
        confirmText="이동"
        cancelText="취소"
        variant="default"
        loading={moveKeywordMutation.isPending}
      />

      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-primary" />
            <h3 className="text-lg font-semibold">keywords.json 편집</h3>
          </div>
          <span className="text-sm text-muted-foreground">
            총 {keywordsData?.total_count || 0}개
          </span>
        </div>

        {/* 새 키워드 추가 폼 */}
        <div className="mb-6 p-4 bg-muted/30 rounded-lg border border-border">
          <div className="flex flex-wrap gap-3">
            <select
              value={newKeywordCategory}
              onChange={(e) => setNewKeywordCategory(e.target.value as 'naver_place' | 'blog_seo')}
              className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="naver_place">🏢 네이버 플레이스</option>
              <option value="blog_seo">📝 블로그 SEO</option>
            </select>
            <input
              type="text"
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              placeholder="새 키워드 입력..."
              className="flex-1 min-w-[200px] px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newKeyword.trim()) {
                  addKeywordMutation.mutate({ keyword: newKeyword.trim(), category: newKeywordCategory })
                }
              }}
            />
            <Button
              variant="primary"
              onClick={() => {
                if (newKeyword.trim()) {
                  addKeywordMutation.mutate({ keyword: newKeyword.trim(), category: newKeywordCategory })
                }
              }}
              disabled={!newKeyword.trim()}
              loading={addKeywordMutation.isPending}
              icon={<Plus className="w-4 h-4" />}
            >
              추가
            </Button>
          </div>
        </div>

        {keywordsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-muted rounded-lg animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 네이버 플레이스 키워드 */}
            <div className="border border-border rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="font-semibold flex items-center gap-2">
                  <span className="text-xl">🏢</span>
                  네이버 플레이스
                </h4>
                <span className="text-sm text-muted-foreground">
                  {keywordsData?.naver_place?.length || 0}개
                </span>
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {keywordsData?.naver_place?.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    등록된 키워드가 없습니다
                  </p>
                ) : (
                  keywordsData?.naver_place?.map((keyword) => (
                    <div
                      key={keyword}
                      className="flex items-center justify-between p-2 bg-muted/50 rounded-lg group hover:bg-muted"
                    >
                      <span className="text-sm">{keyword}</span>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <IconButton
                          icon={<ArrowRightLeft className="w-4 h-4" />}
                          onClick={() => setKeywordToMove({ keyword, from: 'naver_place' })}
                          size="sm"
                          title="블로그 SEO로 이동"
                          className="hover:bg-blue-500/10 text-blue-500"
                        />
                        <IconButton
                          icon={<Trash2 className="w-4 h-4" />}
                          onClick={() => setKeywordToDelete({ keyword, category: 'naver_place' })}
                          size="sm"
                          title="삭제"
                          className="hover:bg-red-500/10 text-red-500"
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* 블로그 SEO 키워드 */}
            <div className="border border-border rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="font-semibold flex items-center gap-2">
                  <span className="text-xl">📝</span>
                  블로그 SEO
                </h4>
                <span className="text-sm text-muted-foreground">
                  {keywordsData?.blog_seo?.length || 0}개
                </span>
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {keywordsData?.blog_seo?.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    등록된 키워드가 없습니다
                  </p>
                ) : (
                  keywordsData?.blog_seo?.map((keyword) => (
                    <div
                      key={keyword}
                      className="flex items-center justify-between p-2 bg-muted/50 rounded-lg group hover:bg-muted"
                    >
                      <span className="text-sm">{keyword}</span>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <IconButton
                          icon={<ArrowRightLeft className="w-4 h-4" />}
                          onClick={() => setKeywordToMove({ keyword, from: 'blog_seo' })}
                          size="sm"
                          title="네이버 플레이스로 이동"
                          className="hover:bg-blue-500/10 text-blue-500"
                        />
                        <IconButton
                          icon={<Trash2 className="w-4 h-4" />}
                          onClick={() => setKeywordToDelete({ keyword, category: 'blog_seo' })}
                          size="sm"
                          title="삭제"
                          className="hover:bg-red-500/10 text-red-500"
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* 안내 메시지 */}
        <div className="mt-6 p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-blue-600 dark:text-blue-400">
            <span className="font-medium">💡 팁:</span> 네이버 플레이스 키워드는 순위 추적에 사용되고, 블로그 SEO 키워드는 콘텐츠 분석에 활용됩니다.
            카테고리 간 이동이 필요하면 이동 버튼을 사용하세요.
          </p>
        </div>
      </div>
    </>
  )
}
