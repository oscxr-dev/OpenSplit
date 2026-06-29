import { Search } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

export type PublicTeamSort = 'splits' | 'active' | 'newest';

const SORTS: Array<{ value: PublicTeamSort; label: string }> = [
  { value: 'splits', label: 'Most splits' },
  { value: 'active', label: 'Recently active' },
  { value: 'newest', label: 'Newest' },
];

interface PublicTeamSearchProps {
  query: string;
  onQueryChange: (value: string) => void;
  sort: PublicTeamSort;
  onSortChange: (value: PublicTeamSort) => void;
}

export function PublicTeamSearch({ query, onQueryChange, sort, onSortChange }: PublicTeamSearchProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/[0.08] bg-white/[0.025] p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:max-w-xs">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
        <Input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search teams by name"
          className="pl-9"
          aria-label="Search teams by name"
        />
      </div>

      <div className="flex items-center gap-2 overflow-x-auto">
        {SORTS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={sort === option.value}
            onClick={() => onSortChange(option.value)}
            className={cn(
              'shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              sort === option.value
                ? 'border border-[#FF2D78]/28 bg-[#FF2D78]/[0.10] text-[#F5F5F7]'
                : 'border border-white/[0.08] bg-white/[0.03] text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
