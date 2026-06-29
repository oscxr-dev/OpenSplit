import { cn } from '@/lib/utils';

type BrandMarkSize = 'xs' | 'sm' | 'lg';

interface BrandMarkProps {
  size?: BrandMarkSize;
  className?: string;
  imageClassName?: string;
}

const sizeStyles: Record<BrandMarkSize, string> = {
  xs: 'h-9 w-9 rounded-lg',
  sm: 'h-10 w-10 rounded-lg',
  lg: 'h-16 w-16 rounded-[18px]',
};

export function BrandMark({ size = 'sm', className, imageClassName }: BrandMarkProps) {
  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center border border-[#FF2D78]/32 bg-[#FF2D78]/10 shadow-[0_0_26px_rgba(255,45,120,0.12)]',
        sizeStyles[size],
        className
      )}
    >
      <img
        src="/brand/OpenSplitlogo.svg"
        alt=""
        aria-hidden="true"
        className={cn('opensplit-logo-icon h-[76%] w-[76%] object-contain', imageClassName)}
      />
    </span>
  );
}
