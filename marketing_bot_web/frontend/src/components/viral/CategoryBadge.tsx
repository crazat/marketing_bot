
interface CategoryBadgeProps {
  category: string;
  size?: 'sm' | 'md' | 'lg';
}

const categoryColors: Record<string, { color: string; bgColor: string }> = {
  '다이어트': { color: 'text-purple-600', bgColor: 'bg-purple-500/10 border-purple-500/30' },
  '비대칭/교정': { color: 'text-indigo-600', bgColor: 'bg-indigo-500/10 border-indigo-500/30' },
  '피부': { color: 'text-pink-600', bgColor: 'bg-pink-500/10 border-pink-500/30' },
  '교통사고': { color: 'text-red-600', bgColor: 'bg-red-500/10 border-red-500/30' },
  '통증/디스크': { color: 'text-orange-600', bgColor: 'bg-orange-500/10 border-orange-500/30' },
  '두통/어지럼': { color: 'text-yellow-600', bgColor: 'bg-yellow-500/10 border-yellow-500/30' },
  '소화기': { color: 'text-green-600', bgColor: 'bg-green-500/10 border-green-500/30' },
  '호흡기': { color: 'text-cyan-600', bgColor: 'bg-cyan-500/10 border-cyan-500/30' },
  '기타증상': { color: 'text-teal-600', bgColor: 'bg-teal-500/10 border-teal-500/30' },
  '기타': { color: 'text-muted-foreground', bgColor: 'bg-muted border-border' },
};

export function CategoryBadge({ category, size = 'md' }: CategoryBadgeProps) {
  const colors = categoryColors[category] || categoryColors['기타'];

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center border rounded-md font-medium ${colors.color} ${colors.bgColor} ${sizeClasses[size]}`}
      title={category}
    >
      {category}
    </span>
  );
}
