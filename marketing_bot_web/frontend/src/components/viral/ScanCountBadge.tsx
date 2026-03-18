
interface ScanCountBadgeProps {
  scanCount: number;
  lastScannedAt?: string;
}

export function ScanCountBadge({ scanCount, lastScannedAt }: ScanCountBadgeProps) {
  if (!scanCount || scanCount < 2) {
    return <span className="text-xs text-muted-foreground">-</span>;
  }

  // 재발견 횟수에 따른 스타일
  let fireIcons = '';
  let colorClass = 'bg-orange-500/10 text-orange-600 border-orange-500/30';
  let pulseClass = '';

  if (scanCount >= 5) {
    fireIcons = '3회+';
    colorClass = 'bg-red-500/10 text-red-600 border-red-500/30';
    pulseClass = 'animate-pulse';
  } else if (scanCount >= 3) {
    fireIcons = '2회+';
    colorClass = 'bg-orange-500/10 text-orange-600 border-orange-500/30';
  }

  const tooltipText = lastScannedAt
    ? `${scanCount}회 재발견\n마지막 스캔: ${new Date(lastScannedAt).toLocaleString('ko-KR')}`
    : `${scanCount}회 재발견`;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 border rounded-full text-xs font-semibold ${colorClass} ${pulseClass}`}
      title={tooltipText}
    >
      <span>{scanCount}회</span>
      {fireIcons && <span className="text-[10px]">({fireIcons})</span>}
    </span>
  );
}
