import type { CSSProperties, ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { cn } from '@/lib/utils';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  logoSrc?: string;
  logoAlt?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Render the confirm button as a destructive (red) action. */
  destructive?: boolean;
  celebrateOnConfirm?: boolean;
  loading?: boolean;
  confirmDisabled?: boolean;
  children?: ReactNode;
  onConfirm: () => void;
  onClose: () => void;
}

const confettiPieces = [
  { x: '-48px', y: '-26px', r: '-34deg' },
  { x: '-34px', y: '22px', r: '28deg' },
  { x: '-18px', y: '-36px', r: '68deg' },
  { x: '0px', y: '30px', r: '-12deg' },
  { x: '18px', y: '-34px', r: '42deg' },
  { x: '34px', y: '20px', r: '-58deg' },
  { x: '48px', y: '-24px', r: '18deg' },
  { x: '-54px', y: '4px', r: '78deg' },
  { x: '54px', y: '4px', r: '-78deg' },
  { x: '-8px', y: '-46px', r: '-8deg' },
  { x: '8px', y: '42px', r: '34deg' },
  { x: '0px', y: '-52px', r: '-44deg' },
];

/**
 * Small, centered, theme-aware confirmation modal — replaces window.confirm.
 * Dark surface in dark mode, clean light surface in light mode (via the Dialog
 * `adaptive` flag). Stacks cleanly on top of an already-open modal.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  logoSrc,
  logoAlt = 'OpenSplit',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  celebrateOnConfirm = false,
  loading = false,
  confirmDisabled = false,
  children,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const [celebrating, setCelebrating] = useState(false);
  const celebrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) setCelebrating(false);

    return () => {
      if (celebrationTimer.current) {
        clearTimeout(celebrationTimer.current);
        celebrationTimer.current = null;
      }
    };
  }, [open]);

  function handleConfirm() {
    if (!celebrateOnConfirm) {
      onConfirm();
      return;
    }

    setCelebrating(true);
    celebrationTimer.current = setTimeout(() => {
      onConfirm();
      setCelebrating(false);
      celebrationTimer.current = null;
    }, 760);
  }

  return (
    <Dialog open={open} onClose={onClose} className="max-w-[23rem]" adaptive>
      <div className="relative overflow-hidden text-center">
        {celebrating && (
          <div className="pointer-events-none absolute inset-x-0 top-1 flex justify-center">
            <div className="os-confetti-burst" aria-hidden="true">
              {confettiPieces.map((piece, index) => (
                <span
                  key={index}
                  style={
                    {
                      '--x': piece.x,
                      '--y': piece.y,
                      '--r': piece.r,
                    } as CSSProperties
                  }
                />
              ))}
            </div>
          </div>
        )}
        {logoSrc && (
          <img
            src={logoSrc}
            alt={logoAlt}
            className="opensplit-wordmark mx-auto mb-4 h-9 w-full max-w-[170px] object-contain"
          />
        )}
        <h2 className="text-base font-semibold tracking-tight text-white">{title}</h2>
        {description && <p className="mx-auto mt-2 max-w-[18rem] text-sm leading-6 text-white/55">{description}</p>}
      </div>
      {children && <div className="mt-4">{children}</div>}
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Button variant="outline" size="sm" onClick={onClose} className="min-w-20">
          {cancelLabel}
        </Button>
        <Button
          variant={destructive ? 'destructive' : 'default'}
          size="sm"
          loading={loading}
          disabled={confirmDisabled}
          onClick={handleConfirm}
          className={cn(
            'min-w-20',
            destructive
              ? 'os-danger-btn'
              : celebrating
                ? 'os-confirm-orange border-transparent bg-orange-500 text-white hover:bg-orange-500'
                : 'os-confirm-primary border-transparent bg-[#FF2D78] text-white hover:bg-[#e9216a]'
          )}
        >
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
