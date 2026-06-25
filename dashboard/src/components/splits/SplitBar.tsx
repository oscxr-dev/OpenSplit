import { cn } from '@/lib/utils';

const SEGMENT_COLORS = [
  'bg-bitcoin',
  'bg-[#8B5CF6]',
  'bg-[#22D3EE]',
  'bg-[#FF77B7]',
  'bg-[#A78BFA]',
  'bg-[#67E8F9]',
];

interface SplitBarTarget {
  label: string;
  percentage: number;
  amount_sats?: number;
}

interface SplitBarProps {
  targets: SplitBarTarget[];
  className?: string;
}

export function SplitBar({ targets, className }: SplitBarProps) {
  if (targets.length === 0) return null;

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-black/20 shadow-[inset_0_1px_2px_rgba(0,0,0,0.25)]">
        {targets.map((target, index) => (
          <div
            key={index}
            className={cn(
              'transition-all duration-500',
              SEGMENT_COLORS[index % SEGMENT_COLORS.length]
            )}
            style={{ width: `${target.percentage}%` }}
            title={`${target.label}: ${target.percentage}%`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {targets.map((target, index) => (
          <div key={index} className="flex items-center gap-1.5 text-xs">
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                SEGMENT_COLORS[index % SEGMENT_COLORS.length]
              )}
            />
            <span className="text-gray-600">{target.label}</span>
            <span className="font-medium text-gray-900">{target.percentage}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
