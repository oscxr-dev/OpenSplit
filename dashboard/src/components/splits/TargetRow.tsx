import { X, Edit3 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TargetRowProps {
  label: string;
  percentage: number;
  color: string;
  onRemove: () => void;
  onEdit: () => void;
}

export function TargetRow({ label, percentage, color, onRemove, onEdit }: TargetRowProps) {
  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors group">
      <span
        className={cn('w-3 h-3 rounded-full flex-shrink-0', color)}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{label}</p>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', color)}
              style={{ width: `${percentage}%` }}
            />
          </div>
          <span className="text-xs font-semibold text-gray-700 tabular-nums">
            {percentage}%
          </span>
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onEdit}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-white transition-colors"
          aria-label="Edit target"
        >
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onRemove}
          className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-white transition-colors"
          aria-label="Delete target"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
