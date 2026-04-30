import { useCallback, useMemo, useState } from 'react';
import { Search, Calendar, Filter, RotateCcw, Clock, Bookmark, BookmarkPlus, X as XIcon } from 'lucide-react';
import { useFilterPresets } from '@/hooks/useFilterPresets';

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
  // [2026-04-27] AI 분류 필터
  ai_ad_label?: string;        // 자연_질문 / 광고 / 광고성_후기톤 / 기타_노이즈 (콤마 가능)
  min_confidence?: number;     // 0.0~1.0
  specialty_match?: string;    // 'high' | 'medium' | 'low' (콤마 가능)
  post_region?: string;        // '청주' | '타지역' | '불명' (콤마 가능)
  work_scope?: 'latest_legion' | 'core' | 'all_backlog';
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
  // [X1] 필터 프리셋
  const { presets, savePreset, removePreset } = useFilterPresets<FilterState>('viral')
  const [showPresetList, setShowPresetList] = useState(false)
  const [savingName, setSavingName] = useState<string | null>(null)

  const handleSavePreset = useCallback(() => {
    const name = savingName?.trim()
    if (!name) return
    savePreset(name, filters)
    setSavingName(null)
  }, [savingName, savePreset, filters])

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
      filters.scan_batch ||
      filters.specialty_match ||
      filters.ai_ad_label ||
      filters.post_region ||
      filters.min_confidence != null
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

  // [V3] 빠른 프리셋 적용
  const applyPreset = useCallback(
    (preset: 'today_pending' | 'today_all' | 'week_posted' | 'hot_only' | 'specialty_high' | 'natural_only' | 'reset') => {
      switch (preset) {
        case 'today_pending':
          onFilterChange({ ...filters, status: 'pending', date_filter: '오늘', sort: 'priority' });
          break;
        case 'today_all':
          onFilterChange({ ...filters, status: undefined, comment_status: undefined, date_filter: '오늘', sort: 'date' });
          break;
        case 'week_posted':
          onFilterChange({ ...filters, status: 'posted', date_filter: '최근 7일', sort: 'date' });
          break;
        case 'hot_only':
          onFilterChange({ ...filters, status: 'pending', sort: 'priority', date_filter: undefined });
          break;
        // [2026-04-27] AI 분류 기반 프리셋
        case 'specialty_high':
          // 미용 특화 매칭 + 자연 질문 + 신뢰도 ≥0.85 (HIGH 큐)
          onFilterChange({
            ...filters,
            status: 'pending',
            comment_status: 'pending',
            specialty_match: 'high',
            sort: 'specialty',
            date_filter: undefined,
          });
          break;
        case 'natural_only':
          // 자연_질문 라벨만 (광고/노이즈 숨김)
          onFilterChange({
            ...filters,
            status: 'pending',
            comment_status: 'pending',
            ai_ad_label: '자연_질문',
            sort: 'specialty',
          });
          break;
        case 'reset':
          onReset();
          break;
      }
    },
    [filters, onFilterChange, onReset]
  );

  return (
    <div className="bg-card border-b border-border p-4 space-y-4">
      {/* [V3] 빠른 프리셋 */}
      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-muted-foreground self-center">⚡ 빠른 필터:</span>
        <button
          onClick={() => applyPreset('today_pending')}
          className="text-xs px-3 py-1.5 rounded-full border border-primary bg-primary/10 text-primary hover:bg-primary/20 font-medium"
          title="오늘 발견된 대기 중 타겟 (가장 일반적)"
        >
          📅 오늘 대기중
        </button>
        <button
          onClick={() => applyPreset('today_all')}
          className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-muted"
          title="오늘 발견 또는 처리한 전체"
        >
          🗓️ 오늘 전체
        </button>
        <button
          onClick={() => applyPreset('week_posted')}
          className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-muted"
          title="최근 7일 게시된 댓글"
        >
          📮 최근 7일 게시됨
        </button>
        <button
          onClick={() => applyPreset('hot_only')}
          className="text-xs px-3 py-1.5 rounded-full border border-red-400/50 bg-red-500/5 text-red-600 dark:text-red-400 hover:bg-red-500/10"
          title="점수 순 대기 HOT LEAD"
        >
          🔥 HOT 대기
        </button>
        {/* [2026-04-27] 미용 특화 큐 — AI 분류 + 우리 강점 카테고리 + 청주 권역 */}
        <button
          onClick={() => applyPreset('specialty_high')}
          className="text-xs px-3 py-1.5 rounded-full border border-orange-400 bg-orange-500/10 text-orange-600 dark:text-orange-400 hover:bg-orange-500/20 font-medium"
          title="다이어트·비대칭·피부·탈모·교통사고 + 청주 권역 + AI 신뢰도 ≥85% 자연 질문"
        >
          🎯 미용 특화 큐
        </button>
        <button
          onClick={() => applyPreset('natural_only')}
          className="text-xs px-3 py-1.5 rounded-full border border-green-400/60 bg-green-500/5 text-green-600 dark:text-green-400 hover:bg-green-500/15"
          title="AI가 자연 질문으로 분류한 것만 (광고/노이즈 숨김)"
        >
          ✓ 자연 질문만
        </button>
        {hasActiveFilters && (
          <button
            onClick={() => applyPreset('reset')}
            className="text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:bg-muted"
          >
            필터 초기화
          </button>
        )}

        {/* [X1] 사용자 프리셋 */}
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => setShowPresetList((v) => !v)}
            className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-muted flex items-center gap-1"
            aria-expanded={showPresetList}
          >
            <Bookmark className="w-3 h-3" />
            내 프리셋 {presets.length > 0 && <span className="text-muted-foreground">({presets.length})</span>}
          </button>
          {hasActiveFilters && (
            <button
              onClick={() => setSavingName('')}
              className="text-xs px-2 py-1.5 rounded-full border border-border hover:bg-muted"
              title="현재 필터 저장"
            >
              <BookmarkPlus className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* [X1] 프리셋 목록 패널 */}
      {showPresetList && (
        <div className="bg-muted/30 border border-border p-3 rounded-lg">
          {presets.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              저장된 프리셋이 없습니다. 현재 필터를 저장해 언제든 복원하세요.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {presets.map((p) => (
                <div
                  key={p.id}
                  className="group flex items-center gap-1 bg-card border border-border px-2.5 py-1 rounded-full text-xs hover:border-primary/50 transition-colors"
                >
                  <button
                    onClick={() => {
                      onFilterChange(p.filters)
                      setShowPresetList(false)
                    }}
                    className="font-medium"
                  >
                    {p.name}
                  </button>
                  <button
                    onClick={() => removePreset(p.id)}
                    className="opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
                    aria-label={`${p.name} 삭제`}
                  >
                    <XIcon className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* [X1] 저장 이름 입력 */}
      {savingName !== null && (
        <div className="bg-primary/5 border border-primary/30 p-3 rounded-lg flex items-center gap-2">
          <BookmarkPlus className="w-4 h-4 text-primary shrink-0" />
          <input
            autoFocus
            type="text"
            value={savingName}
            onChange={(e) => setSavingName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSavePreset()
              if (e.key === 'Escape') setSavingName(null)
            }}
            placeholder="프리셋 이름 (예: 청주 HOT 블로그)"
            className="flex-1 bg-transparent border-b border-border focus:outline-none focus:border-primary text-sm px-1 py-1"
            maxLength={30}
          />
          <button
            onClick={handleSavePreset}
            disabled={!savingName.trim()}
            className="text-xs px-3 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            저장
          </button>
          <button
            onClick={() => setSavingName(null)}
            className="text-xs px-2 py-1 rounded hover:bg-muted"
          >
            취소
          </button>
        </div>
      )}

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
