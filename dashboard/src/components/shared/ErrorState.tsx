import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  message = 'Something went wrong',
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex min-h-72 flex-col items-center justify-center rounded-2xl border border-red-300/10 bg-red-400/[0.04] px-4 py-16 text-center',
        className
      )}
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-400/10">
        <AlertTriangle className="w-8 h-8 text-red-500" />
      </div>
      <h3 className="mb-1 text-lg font-medium text-white/85">Error</h3>
      <p className="mb-6 max-w-sm text-sm text-white/40">{message}</p>
      {onRetry && (
        <Button onClick={onRetry} variant="outline" size="sm">
          Retry
        </Button>
      )}
    </div>
  );
}
