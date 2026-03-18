import { Inbox, Filter, RefreshCw } from 'lucide-react';

interface EmptyStateProps {
  type: 'no-targets' | 'no-results' | 'all-done';
  onAction?: () => void;
  actionLabel?: string;
}

export function EmptyState({ type, onAction, actionLabel }: EmptyStateProps) {
  const configs = {
    'no-targets': {
      icon: <Inbox className="w-16 h-16 text-muted-foreground/50" />,
      title: '아직 타겟이 없습니다',
      description: '먼저 스캔을 실행하여 바이럴 타겟을 발굴하세요',
      actionLabel: actionLabel || '스캔 실행',
    },
    'no-results': {
      icon: <Filter className="w-16 h-16 text-muted-foreground/50" />,
      title: '검색 결과가 없습니다',
      description: '필터 조건을 변경하거나 검색어를 수정해보세요',
      actionLabel: actionLabel || '필터 초기화',
    },
    'all-done': {
      icon: <RefreshCw className="w-16 h-16 text-green-500" />,
      title: '모든 타겟 처리 완료!',
      description: '새로운 타겟을 발굴하려면 스캔을 다시 실행하세요',
      actionLabel: actionLabel || '홈으로',
    },
  };

  const config = configs[type];

  return (
    <div className="flex flex-col items-center justify-center p-12 bg-card border border-border rounded-lg">
      <div className="mb-4">{config.icon}</div>
      <h3 className="text-xl font-semibold text-foreground mb-2">{config.title}</h3>
      <p className="text-sm text-muted-foreground mb-6 text-center max-w-md">{config.description}</p>
      {onAction && (
        <button
          onClick={onAction}
          className="px-6 py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
        >
          {config.actionLabel}
        </button>
      )}
    </div>
  );
}
