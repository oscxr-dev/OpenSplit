import { cn } from '@/lib/utils';

type BadgeVariant = 'default' | 'success' | 'warning' | 'error';

interface BadgeProps {
  variant?: BadgeVariant;
  children: string;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'border-white/10 bg-white/[0.07] text-white/60',
  success: 'border-emerald-300/15 bg-emerald-400/10 text-emerald-300',
  warning: 'border-amber-300/15 bg-amber-400/10 text-amber-200',
  error: 'border-red-300/15 bg-red-400/10 text-red-300',
};

const statusMap: Record<string, BadgeVariant> = {
  paid: 'success',
  pending: 'warning',
  'in progress': 'warning',
  completed: 'success',
  cancelled: 'error',
  failed: 'error',
  active: 'success',
  inactive: 'default',
};

export function Badge({ variant = 'default', children, className }: BadgeProps) {
  const resolvedVariant = statusMap[children.toLowerCase()] || variant;
  const dotStyles: Record<BadgeVariant, string> = {
    default: 'bg-white/35',
    success: 'bg-emerald-400',
    warning: 'bg-amber-300',
    error: 'bg-red-400',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium',
        variantStyles[resolvedVariant],
        className
      )}
    >
      <span className={cn('mr-1.5 h-1.5 w-1.5 rounded-full', dotStyles[resolvedVariant])} />
      {children}
    </span>
  );
}
