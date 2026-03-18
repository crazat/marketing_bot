import { useCallback, useMemo } from 'react';
import { Search, Calendar, Filter, RotateCcw, Clock } from 'lucide-react';

export interface FilterState {
  date_filter?: string;
  platforms?: string[];
  status?: string;
  category?: string;           // 카테고리 필터 추가
  comment_status?: string;     // 댓글 상태 필터 추가
  min_scan_count?: number;
  search?: string;
  sort?: string;
  scan_batch?: string;
}

export interface ScanBatch {
  batch_id: string;
  batch_label: string;
  batch_date: string;
  batch_hour: number;
  count: number;
}

interface FilterBarProps {
  filters: FilterState;
  onFilterChange: (filters: FilterState) => void;
  onReset: () => void;
  scanBatches?: ScanBatch[];
}

export function FilterBar({ filters, onFilterChange, onReset, scanBatches = [] }: FilterBarProps) {
  // [Phase 7] useCallback으로 메모이제이션 - 불필요한 리렌더링 방지
  const handlePlatformToggle = useCallback((platform: string) => {
    const current = filters.platforms || [];
    const updated = current.includes(platform)
      ? current.filter(p => p !== platform)
      : [...current, platform];
    onFilterChange({ ...filters, platforms: updated });
  }, [filters, onFilterChange]);

  const isPlatformSelected = useCallback((platform: string) => {
    return filters.platforms?.includes(platform) || false;
  }, [filters.platforms]);

  // [Phase 7] useMemo로 계산 결과 캐싱
  const hasActiveFilters = useMemo(() => {
    return (
      filters.date_filter ||
      (filters.platforms && filters.platforms.length > 0) ||
      filters.category ||
      filters.comment_status ||
      filters.min_scan_count ||
      filters.search ||
      (filters.sort && filters.sort !== 'priority') ||
      filters.scan_batch
    );
  }, [filters]);

  // 플랫폼 라벨 매핑 (8개 플랫폼)
  const platformLabels: Record<string, string> = {
    cafe: '카페',
    blog: '블로그',
    kin: '지식인',
    youtube: 'YouTube',
    instagram: '인스타',
    tiktok: 'TikTok',
    place: '플레이스',
    karrot: '당근'
  };

  // 카테고리 목록 (11개 - 전체 시스템 통일)
  const categories = [
    '다이어트', '비대칭/교정', '피부', '교통사고',
    '통증/디스크', '두통/어지럼', '소화기', '호흡기',
    '탈모', '여성건강', '기타'
  ];

  // 댓글 상태 옵션
  const commentStatusOptions = [
    { value: 'pending', label: '대기중' },
    { value: 'generated', label: 'AI 생성됨' },
    { value: 'approved', label: '승인됨' },
    { value: 'posted', label: '게시됨' },
    { value: 'skipped', label: '건너뜀' }
  ];

  return (
    <div className="bg-card border-b border-border p-4 space-y-4">
      {/* 검색 */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
        <input
          type="text"
          value={filters.search || ''}
          onChange={(e) => onFilterChange({ ...filters, search: e.target.value })}
          placeholder="제목 또는 내용 검색..."
          aria-label="제목 또는 내용 검색"
          className="w-full pl-10 pr-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      {/* 필터 그룹 */}
      <div className="flex flex-wrap gap-4 items-center">
        {/* 스캔 히스토리 필터 */}
        {scanBatches.length > 0 && (
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <select
              value={filters.scan_batch || ''}
              onChange={(e) => onFilterChange({
                ...filters,
                scan_batch: e.target.value || undefined,
                date_filter: undefined  // 스캔 배치 선택 시 날짜 필터 해제
              })}
              aria-label="스캔 히스토리 선택"
              className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">전체 스캔</option>
              {scanBatches.map((batch) => (
                <option key={batch.batch_id} value={batch.batch_id}>
                  {batch.batch_label}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* 날짜 필터 */}
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
          <select
            value={filters.date_filter || ''}
            onChange={(e) => onFilterChange({
              ...filters,
              date_filter: e.target.value || undefined,
              scan_batch: undefined  // 날짜 필터 선택 시 스캔 배치 해제
            })}
            aria-label="날짜 필터"
            className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            disabled={!!filters.scan_batch}  // 스캔 배치 선택 시 비활성화
          >
            <option value="">전체 기간</option>
            <option value="오늘">오늘</option>
            <option value="최근 7일">최근 7일</option>
            <option value="최근 30일">최근 30일</option>
          </select>
        </div>

        {/* 플랫폼 필터 (8개) */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="플랫폼 필터">
            {['cafe', 'blog', 'kin', 'youtube', 'instagram', 'tiktok', 'place', 'karrot'].map((platform) => (
              <button
                key={platform}
                onClick={() => handlePlatformToggle(platform)}
                aria-pressed={isPlatformSelected(platform)}
                className={`px-2 py-1 text-xs rounded-md border focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-primary transition-colors ${
                  isPlatformSelected(platform)
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-foreground border-border hover:bg-muted'
                }`}
              >
                {platformLabels[platform]}
              </button>
            ))}
          </div>
        </div>

        {/* 카테고리 필터 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground" id="category-label">카테고리</span>
          <select
            value={filters.category || ''}
            onChange={(e) => onFilterChange({ ...filters, category: e.target.value || undefined })}
            aria-labelledby="category-label"
            className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">전체</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>

        {/* 댓글 상태 필터 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground" id="comment-status-label">댓글상태</span>
          <select
            value={filters.comment_status || ''}
            onChange={(e) => onFilterChange({ ...filters, comment_status: e.target.value || undefined })}
            aria-labelledby="comment-status-label"
            className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">전체</option>
            {commentStatusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* 재발견 필터 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground" id="scan-count-label">재발견</span>
          <select
            value={filters.min_scan_count || 0}
            onChange={(e) => onFilterChange({ ...filters, min_scan_count: parseInt(e.target.value) || undefined })}
            aria-labelledby="scan-count-label"
            className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="0">전체</option>
            <option value="2">2회 이상</option>
            <option value="3">3회 이상</option>
            <option value="5">5회 이상</option>
          </select>
        </div>

        {/* 정렬 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground" id="sort-label">정렬</span>
          <select
            value={filters.sort || 'priority'}
            onChange={(e) => onFilterChange({ ...filters, sort: e.target.value })}
            aria-labelledby="sort-label"
            className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="priority">우선순위</option>
            <option value="date">최신순</option>
            <option value="scan_count">재발견순</option>
          </select>
        </div>

        {/* 초기화 버튼 */}
        {hasActiveFilters && (
          <button
            onClick={onReset}
            className="ml-auto px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 border border-border rounded-lg hover:bg-muted focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
            aria-label="필터 초기화"
          >
            <RotateCcw className="w-4 h-4" />
            초기화
          </button>
        )}
      </div>
    </div>
  );
}
