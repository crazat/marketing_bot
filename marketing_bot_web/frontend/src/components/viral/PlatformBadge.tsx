
interface PlatformBadgeProps {
  platform: string;
  size?: 'sm' | 'md' | 'lg';
}

const platformConfig: Record<string, { icon: string; label: string; color: string; bgColor: string }> = {
  cafe: {
    icon: '',
    label: '카페',
    color: 'text-amber-600',
    bgColor: 'bg-amber-500/10 border-amber-500/30',
  },
  blog: {
    icon: '',
    label: '블로그',
    color: 'text-green-600',
    bgColor: 'bg-green-500/10 border-green-500/30',
  },
  kin: {
    icon: '',
    label: '지식인',
    color: 'text-blue-600',
    bgColor: 'bg-blue-500/10 border-blue-500/30',
  },
  instagram: {
    icon: '',
    label: '인스타',
    color: 'text-pink-600',
    bgColor: 'bg-pink-500/10 border-pink-500/30',
  },
};

export function PlatformBadge({ platform, size = 'md' }: PlatformBadgeProps) {
  const config = platformConfig[platform] || {
    icon: '',
    label: platform,
    color: 'text-muted-foreground',
    bgColor: 'bg-muted border-border',
  };

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center gap-1 border rounded-md font-medium ${config.color} ${config.bgColor} ${sizeClasses[size]}`}
      title={config.label}
    >
      {config.icon && <span>{config.icon}</span>}
      <span>{config.label}</span>
    </span>
  );
}
