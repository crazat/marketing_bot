import { useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { battleApi } from '@/services/api'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import { useFormValidation } from '@/hooks/useFormValidation'

interface EditKeywordModalProps {
  keyword: string
  currentCategory?: string
  onClose: () => void
  onSuccess: () => void
}

interface FormValues {
  newKeyword: string
  category: string
}

export default function EditKeywordModal({
  keyword,
  currentCategory = '기타',
  onClose,
  onSuccess
}: EditKeywordModalProps) {
  const initialValues = useMemo(() => ({
    newKeyword: keyword,
    category: currentCategory,
  }), [keyword, currentCategory])

  const form = useFormValidation<FormValues>(
    {
      newKeyword: {
        required: '키워드를 입력해주세요',
        minLength: { value: 2, message: '최소 2글자 이상 입력해주세요' },
        maxLength: { value: 50, message: '50글자 이하로 입력해주세요' },
      },
      category: {},
    },
    initialValues
  )

  const updateKeyword = useMutation({
    mutationFn: () =>
      battleApi.updateRankingKeyword(keyword, form.values.newKeyword, form.values.category),
    onSuccess: () => {
      onSuccess()
    },
    onError: (err: Error & { message?: string }) => {
      form.setError('newKeyword', err.message || '키워드 수정에 실패했습니다.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.validateAll()) return
    updateKeyword.mutate()
  }

  const handleClose = () => {
    form.reset()
    onClose()
  }

  const hasChanges =
    form.values.newKeyword !== keyword ||
    form.values.category !== currentCategory

  const newKeywordProps = form.getFieldProps('newKeyword')
  const categoryProps = form.getFieldProps('category')

  return (
    <Modal
      isOpen={true}
      onClose={handleClose}
      title="✏️ 키워드 수정"
      size="md"
      footer={
        <div className="flex gap-3 w-full">
          <Button
            type="button"
            onClick={handleClose}
            variant="secondary"
            fullWidth
          >
            취소
          </Button>
          <Button
            type="submit"
            form="edit-keyword-form"
            disabled={!hasChanges}
            loading={updateKeyword.isPending}
            fullWidth
          >
            수정
          </Button>
        </div>
      }
    >
      <form id="edit-keyword-form" onSubmit={handleSubmit} className="space-y-4">
        <p className="text-xs text-muted-foreground">
          <span className="text-red-500" aria-hidden="true">*</span> 표시는 필수 입력 항목입니다
        </p>

        {/* 기존 키워드 표시 */}
        <div>
          <label className="block text-sm font-medium mb-2">기존 키워드</label>
          <div className="px-3 py-2 bg-muted/50 border border-border rounded-lg text-muted-foreground">
            {keyword}
          </div>
        </div>

        {/* 새 키워드 입력 */}
        <div>
          <label htmlFor="new-keyword-input" className="block text-sm font-medium mb-2">
            새 키워드 <span className="text-red-500" aria-hidden="true">*</span>
          </label>
          <input
            id="new-keyword-input"
            type="text"
            value={newKeywordProps.value as string}
            onChange={newKeywordProps.onChange}
            onBlur={newKeywordProps.onBlur}
            placeholder="수정할 키워드 입력"
            className={`w-full px-3 py-2 bg-background border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 transition-colors ${
              newKeywordProps.error
                ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                : 'border-border focus:border-primary'
            }`}
            aria-required="true"
            aria-invalid={newKeywordProps['aria-invalid']}
            aria-describedby="keyword-hint new-keyword-error"
          />
          <p id="keyword-hint" className="text-xs text-muted-foreground mt-1">
            띄어쓰기 여부에 따라 검색량이 달라질 수 있습니다
          </p>
          {newKeywordProps.error && (
            <p id="new-keyword-error" className="mt-1.5 text-sm text-red-500 flex items-center gap-1" role="alert">
              <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {newKeywordProps.error}
            </p>
          )}
        </div>

        {/* 카테고리 선택 */}
        <div>
          <label htmlFor="edit-category-select" className="block text-sm font-medium mb-2">
            카테고리
          </label>
          <select
            id="edit-category-select"
            value={categoryProps.value as string}
            onChange={categoryProps.onChange}
            onBlur={categoryProps.onBlur}
            className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
          >
            <option value="기타">기타</option>
            <option value="다이어트">다이어트</option>
            <option value="비대칭/교정">비대칭/교정</option>
            <option value="피부">피부</option>
            <option value="교통사고">교통사고</option>
            <option value="통증/디스크">통증/디스크</option>
            <option value="두통/어지럼">두통/어지럼</option>
            <option value="소화기">소화기</option>
            <option value="호흡기">호흡기</option>
            <option value="탈모">탈모</option>
            <option value="여성건강">여성건강</option>
          </select>
        </div>

        {/* API 에러 메시지 */}
        {updateKeyword.isError && (
          <div
            className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm flex items-center gap-2"
            role="alert"
          >
            <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            수정 실패: {(updateKeyword.error as Error).message}
          </div>
        )}
      </form>
    </Modal>
  )
}
