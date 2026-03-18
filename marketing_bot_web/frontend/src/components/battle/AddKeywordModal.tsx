import { useMutation } from '@tanstack/react-query'
import { battleApi } from '@/services/api'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import { useFormValidation } from '@/hooks/useFormValidation'

interface AddKeywordModalProps {
  onClose: () => void
  onSuccess: () => void
}

interface FormValues {
  keyword: string
  targetRank: number
  category: string
}

export default function AddKeywordModal({ onClose, onSuccess }: AddKeywordModalProps) {
  const form = useFormValidation<FormValues>(
    {
      keyword: {
        required: '키워드를 입력해주세요',
        minLength: { value: 2, message: '최소 2글자 이상 입력해주세요' },
        maxLength: { value: 50, message: '50글자 이하로 입력해주세요' },
      },
      targetRank: {
        required: '목표 순위를 입력해주세요',
        min: { value: 1, message: '1 이상의 순위를 입력해주세요' },
        max: { value: 100, message: '100 이하의 순위를 입력해주세요' },
      },
      category: {},
    },
    {
      keyword: '',
      targetRank: 10,
      category: '기타',
    }
  )

  const addKeyword = useMutation({
    mutationFn: () =>
      battleApi.addRankingKeyword(
        form.values.keyword,
        form.values.targetRank,
        form.values.category
      ),
    onSuccess: () => {
      form.reset()
      onSuccess()
    },
    onError: (err: Error & { message?: string }) => {
      form.setError('keyword', err.message || '키워드 추가에 실패했습니다. 다시 시도해주세요.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.validateAll()) return
    addKeyword.mutate()
  }

  const handleClose = () => {
    form.reset()
    onClose()
  }

  const keywordProps = form.getFieldProps('keyword')
  const targetRankProps = form.getFieldProps('targetRank')
  const categoryProps = form.getFieldProps('category')

  return (
    <Modal
      isOpen={true}
      onClose={handleClose}
      title="🎯 순위 추적 키워드 추가"
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
            form="add-keyword-form"
            disabled={!form.isDirty}
            loading={addKeyword.isPending}
            fullWidth
          >
            추가
          </Button>
        </div>
      }
    >
      <form id="add-keyword-form" onSubmit={handleSubmit} className="space-y-4">
        <p className="text-xs text-muted-foreground">
          <span className="text-red-500" aria-hidden="true">*</span> 표시는 필수 입력 항목입니다
        </p>

        {/* 키워드 입력 */}
        <div>
          <label htmlFor="keyword-input" className="block text-sm font-medium mb-2">
            키워드 <span className="text-red-500" aria-hidden="true">*</span>
          </label>
          <input
            id="keyword-input"
            type="text"
            value={keywordProps.value as string}
            onChange={keywordProps.onChange}
            onBlur={keywordProps.onBlur}
            placeholder="예: 청주 한의원"
            className={`w-full px-3 py-2 bg-background border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 transition-colors ${
              keywordProps.error
                ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                : 'border-border focus:border-primary'
            }`}
            aria-required="true"
            aria-invalid={keywordProps['aria-invalid']}
            aria-describedby={keywordProps.error ? 'keyword-error' : undefined}
          />
          {keywordProps.error && (
            <p id="keyword-error" className="mt-1.5 text-sm text-red-500 flex items-center gap-1" role="alert">
              <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {keywordProps.error}
            </p>
          )}
        </div>

        {/* 목표 순위 입력 */}
        <div>
          <label htmlFor="target-rank-input" className="block text-sm font-medium mb-2">
            목표 순위 <span className="text-red-500" aria-hidden="true">*</span>
          </label>
          <input
            id="target-rank-input"
            type="number"
            value={targetRankProps.value as number}
            onChange={targetRankProps.onChange}
            onBlur={targetRankProps.onBlur}
            min={1}
            max={100}
            className={`w-full px-3 py-2 bg-background border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 transition-colors ${
              targetRankProps.error
                ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                : 'border-border focus:border-primary'
            }`}
            aria-required="true"
            aria-invalid={targetRankProps['aria-invalid']}
            aria-describedby={targetRankProps.error ? 'target-rank-error' : undefined}
          />
          {targetRankProps.error && (
            <p id="target-rank-error" className="mt-1.5 text-sm text-red-500 flex items-center gap-1" role="alert">
              <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {targetRankProps.error}
            </p>
          )}
        </div>

        {/* 카테고리 선택 */}
        <div>
          <label htmlFor="category-select" className="block text-sm font-medium mb-2">
            카테고리
          </label>
          <select
            id="category-select"
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
        {addKeyword.isError && (
          <div
            className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm flex items-center gap-2"
            role="alert"
          >
            <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            {(addKeyword.error as Error).message || '키워드 추가에 실패했습니다.'}
          </div>
        )}
      </form>
    </Modal>
  )
}
