interface CommandInfo {
  description: string;
  command: string | string[];
  dbTable?: string;
  dbCountQuery?: string;
  expectedOutput?: string;
  note?: string;
}

/**
 * Linux 경로를 Windows 경로로 변환
 * /mnt/c/Projects/... -> C:\Projects\...
 */
export function toWindowsPath(linuxPath: string): string {
  if (linuxPath.startsWith('/mnt/')) {
    const parts = linuxPath.split('/');
    const driveLetter = parts[2].toUpperCase();
    const restPath = parts.slice(3).join('\\');
    return `${driveLetter}:\\${restPath}`;
  }
  return linuxPath;
}

/**
 * 주요 명령어 매핑
 * schedule.json의 commands 섹션과 동기화
 */
const COMMANDS: Record<string, string> = {
  pathfinder: 'python pathfinder_v3_complete.py --save-db',
  pathfinder_legion: 'python pathfinder_v3_legion.py --target 500 --save-db',
  viral_hunter: 'python viral_hunter.py --scan',
  place_sniper: 'python scrapers/scraper_naver_place.py',
  weakness_analyzer: 'python competitor_weakness_analyzer.py',
  lead_manager: 'python lead_manager.py',
};

/**
 * 명령어 키로 실제 명령어 문자열 반환
 */
export function getCommand(cmdKey: string): string {
  return COMMANDS[cmdKey] || '';
}

/**
 * DB 테이블별 검증 명령어 생성
 */
export function getDbCheckCommand(table: string, sinceMinutes?: number): string {
  let cmd = `python utils/check_db.py --table ${table}`;
  if (sinceMinutes) {
    cmd += ` --since ${sinceMinutes}`;
  }
  return cmd;
}

/**
 * 페이지별 터미널 명령어 반환
 */
export function getPageCommands(page: string): CommandInfo[] {
  switch (page) {
    case 'pathfinder':
      return [
        {
          description: 'Total War 모드 - 빠른 키워드 수집 (약 5분)',
          command: getCommand('pathfinder'),
          dbTable: 'keyword_insights',
          dbCountQuery: getDbCheckCommand('keyword_insights', 10),
          expectedOutput: 'S/A/B/C 등급별 키워드 개수 표시',
          note: '약 50-100개의 키워드를 빠르게 수집합니다.',
        },
        {
          description: 'LEGION 모드 - 대량 키워드 수집 (약 15-30분)',
          command: getCommand('pathfinder_legion'),
          dbTable: 'keyword_insights',
          dbCountQuery: 'python utils/check_db.py --verify-scan pathfinder',
          expectedOutput: '목표 개수(500개)에 도달할 때까지 수집',
          note: '더 많은 키워드가 필요할 때 사용합니다. 실행 시간이 길 수 있습니다.',
        },
      ];

    case 'viral':
      return [
        {
          description: 'Viral Hunter 스캔 - 바이럴 콘텐츠 수집',
          command: getCommand('viral_hunter'),
          dbTable: 'viral_targets',
          dbCountQuery: getDbCheckCommand('viral_targets', 15),
          expectedOutput: '플랫폼별 바이럴 타겟 개수 표시',
          note: '네이버 블로그/카페, 인스타그램 등에서 잠재고객 발굴',
        },
      ];

    case 'battle':
      return [
        {
          description: 'Place Sniper - 네이버 플레이스 순위 스캔',
          command: getCommand('place_sniper'),
          dbTable: 'rank_history',
          dbCountQuery: 'python utils/check_db.py --table rank_history --latest 10',
          expectedOutput: '키워드별 모바일/데스크탑 순위 표시',
          note: '모바일과 데스크탑 순위를 각각 수집합니다.',
        },
      ];

    case 'competitors':
      return [
        {
          description: 'Weakness Analyzer - 경쟁사 약점 분석',
          command: getCommand('weakness_analyzer'),
          dbTable: 'competitor_weaknesses',
          dbCountQuery: getDbCheckCommand('competitor_weaknesses'),
          expectedOutput: '약점 유형별 분석 결과 표시',
          note: 'Gemini AI를 사용하여 리뷰에서 약점을 추출합니다.',
        },
      ];

    case 'leads':
      return [
        {
          description: 'Lead Manager - 리드 수집 및 분류',
          command: getCommand('lead_manager'),
          dbTable: 'leads',
          dbCountQuery: getDbCheckCommand('leads'),
          expectedOutput: '플랫폼별 리드 개수 및 상태 표시',
          note: '6개 플랫폼에서 잠재고객을 수집합니다.',
        },
      ];

    default:
      return [];
  }
}

/**
 * 스캔 실행 기록 확인 명령어
 */
export function getScanRunsCommand(): string {
  return 'python utils/check_db.py --scan-runs';
}

/**
 * 전체 요약 명령어
 */
export function getSummaryCommand(): string {
  return 'python utils/check_db.py --summary';
}
