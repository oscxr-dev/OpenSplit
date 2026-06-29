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

type SplitBarVariant = 'default' | 'pink' | 'library';

interface SplitBarProps {
  targets: SplitBarTarget[];
  className?: string;
  /**
   * 'pink' homologates every segment to OpenSplit electric-pink variations
   * (used only by the Current Rule visualization). Larger shares become softer
   * and lighter; smaller shares stay stronger and more saturated.
   * 'library' restricts segments to only electric-pink/orange/yellow/green
   * families, cycling through tonal variations of those four for 5+ participants
   * (used by the Rule Library preview bars). Default keeps the original
   * multi-color palette used elsewhere (POS, splits page).
   */
  variant?: SplitBarVariant;
  /** Hide the per-target legend for compact previews (e.g. Rule Library rows). */
  showLegend?: boolean;
}

// Electric-pink hue shared with the OpenSplit accent (#FF2D78 ≈ hsl(336, 100%, 59%)).
const PINK_HUE = 336;

function pinkShade(percentage: number, index: number): string {
  const ratio = Math.min(Math.max(percentage, 0), 100) / 100;
  // Bigger share -> lighter + a touch less saturated (softer).
  const lightness = 56 + ratio * 22 + (index % 3) * 3;
  const saturation = 92 - ratio * 22;
  return `hsl(${PINK_HUE}, ${saturation.toFixed(0)}%, ${lightness.toFixed(0)}%)`;
}

// Only electric-pink / orange / yellow / green — the four allowed families. The
// first four are the base tones (one per family); each further cycle of four
// reuses the same families in a different tone (darker, then lighter) so 5+
// segments stay distinct without introducing any new colors. Pink shades are the
// OpenSplit accent (bitcoin 500/700/300).
const LIBRARY_SHADES = [
  '#FF2D78', '#F97316', '#EAB308', '#22C55E', // base   (pink/orange/yellow/green)
  '#BD0F55', '#C2410C', '#A16207', '#15803D', // darker
  '#FF8FCC', '#FDBA74', '#FDE047', '#86EFAC', // lighter
];

function libraryColor(index: number): string {
  return LIBRARY_SHADES[index % LIBRARY_SHADES.length];
}

export function SplitBar({ targets, className, variant = 'default', showLegend = true }: SplitBarProps) {
  if (targets.length === 0) return null;

  // Variants that paint segments via inline color rather than a CSS class.
  const customColor = (target: SplitBarTarget, index: number): string | undefined => {
    if (variant === 'pink') return pinkShade(target.percentage, index);
    if (variant === 'library') return libraryColor(index);
    return undefined;
  };
  const segmentStyle = (target: SplitBarTarget, index: number) => {
    const color = customColor(target, index);
    return color ? { width: `${target.percentage}%`, backgroundColor: color } : { width: `${target.percentage}%` };
  };
  const dotStyle = (target: SplitBarTarget, index: number) => {
    const color = customColor(target, index);
    return color ? { backgroundColor: color } : undefined;
  };
  const segmentClass = (target: SplitBarTarget, index: number) =>
    customColor(target, index) ? '' : SEGMENT_COLORS[index % SEGMENT_COLORS.length];

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-black/20 shadow-[inset_0_1px_2px_rgba(0,0,0,0.25)]">
        {targets.map((target, index) => (
          <div
            key={index}
            className={cn('transition-all duration-500', segmentClass(target, index))}
            style={segmentStyle(target, index)}
            title={`${target.label}: ${target.percentage}%`}
          />
        ))}
      </div>
      {showLegend && (
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {targets.map((target, index) => (
          <div key={index} className="flex items-center gap-1.5 text-xs">
            <span
              className={cn('w-2 h-2 rounded-full', segmentClass(target, index))}
              style={dotStyle(target, index)}
            />
            <span className="text-gray-600">{target.label}</span>
            <span className="font-medium text-gray-900">{target.percentage}%</span>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
