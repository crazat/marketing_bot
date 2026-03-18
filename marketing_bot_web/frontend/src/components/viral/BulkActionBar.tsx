import { CheckSquare, XSquare, Trash2, AlertCircle, Sparkles } from 'lucide-react';
import Button from '@/components/ui/Button';

interface BulkActionBarProps {
  selectedCount: number;
  totalCount: number;
  onApprove: () => void;
  onSkip: () => void;
  onDelete: () => void;
  onGenerateComments?: () => void;
  onClearSelection: () => void;
  isProcessing?: boolean;
  isGenerating?: boolean;
  generationProgress?: { current: number; total: number };
}

export function BulkActionBar({
  selectedCount,
  totalCount,
  onApprove,
  onSkip,
  onDelete,
  onGenerateComments,
  onClearSelection,
  isProcessing = false,
  isGenerating = false,
  generationProgress,
}: BulkActionBarProps) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-6 left-4 right-4 md:left-1/2 md:right-auto md:-translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 duration-300">
      <div className="bg-card border-2 border-primary rounded-lg shadow-2xl p-3 md:p-4 md:min-w-[500px]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 md:gap-4">
          {/* 선택 정보 */}
          <div className="flex items-center gap-3">
            <div className="bg-primary text-primary-foreground rounded-full w-8 h-8 flex items-center justify-center font-bold text-sm">
              {selectedCount}
            </div>
            <div>
              <p className="font-semibold text-foreground text-sm md:text-base">
                {selectedCount}개 타겟 선택됨
              </p>
              <p className="text-xs text-muted-foreground">
                전체 {totalCount}개 중
              </p>
            </div>
          </div>

          {/* 액션 버튼 */}
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto" role="group" aria-label="일괄 작업">
            {/* AI 댓글 일괄 생성 버튼 */}
            {onGenerateComments && (
              <Button
                onClick={onGenerateComments}
                disabled={isProcessing || isGenerating}
                loading={isGenerating}
                icon={<Sparkles className="w-4 h-4" />}
                className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white"
              >
                <span className="hidden sm:inline">AI 댓글 생성</span>
                <span className="sm:hidden">AI</span>
              </Button>
            )}

            <div className="hidden sm:block w-px h-6 bg-border mx-1" />

            <Button
              variant="success"
              onClick={onApprove}
              disabled={isProcessing || isGenerating}
              icon={<CheckSquare className="w-4 h-4" />}
            >
              <span className="hidden sm:inline">일괄 승인</span>
              <span className="sm:hidden">승인</span>
            </Button>

            <Button
              onClick={onSkip}
              disabled={isProcessing || isGenerating}
              icon={<XSquare className="w-4 h-4" />}
              className="bg-yellow-600 hover:bg-yellow-700 text-white"
            >
              <span className="hidden sm:inline">일괄 건너뛰기</span>
              <span className="sm:hidden">건너뛰기</span>
            </Button>

            <Button
              variant="danger"
              onClick={onDelete}
              disabled={isProcessing || isGenerating}
              icon={<Trash2 className="w-4 h-4" />}
            >
              <span className="hidden sm:inline">일괄 삭제</span>
              <span className="sm:hidden">삭제</span>
            </Button>

            <Button
              variant="ghost"
              onClick={onClearSelection}
              disabled={isProcessing || isGenerating}
              className="ml-auto sm:ml-2"
            >
              취소
            </Button>
          </div>
        </div>

        {/* 처리 중 표시 */}
        {isProcessing && (
          <div className="mt-3 pt-3 border-t border-border flex items-center gap-2 text-sm text-muted-foreground">
            <AlertCircle className="w-4 h-4 animate-pulse" />
            <span>처리 중입니다... 잠시만 기다려주세요.</span>
          </div>
        )}

        {/* AI 생성 진행률 표시 */}
        {isGenerating && generationProgress && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-muted-foreground flex items-center gap-2">
                <Sparkles className="w-4 h-4 animate-pulse text-purple-500" />
                AI 댓글 생성 중...
              </span>
              <span className="font-medium text-foreground">
                {generationProgress.current} / {generationProgress.total}
              </span>
            </div>
            <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-purple-500 to-blue-500 h-2 rounded-full transition-all duration-300"
                style={{
                  width: `${(generationProgress.current / generationProgress.total) * 100}%`
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
