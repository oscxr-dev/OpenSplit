import { type ReactNode, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
  /** Opt in to a clean LIGHT surface when the app is in light mode (see the
   *  .os-modal-light rules in globals.css). Default keeps the always-dark modal. */
  adaptive?: boolean;
}

export function Dialog({ open, onClose, title, children, className, adaptive = false }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;

    if (open) {
      el.showModal();
    } else {
      el.close();
    }
  }, [open]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;

    const handleClose = () => onClose();
    el.addEventListener('close', handleClose);
    return () => el.removeEventListener('close', handleClose);
  }, [onClose]);

  return (
    <dialog
      ref={dialogRef}
      className={cn(
        'os-modal fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-1.5rem)] max-w-lg overflow-y-auto rounded-3xl border border-white/[0.16] bg-[#1b1825] p-0 text-white shadow-[0_30px_110px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.12)] backdrop:bg-black/80 backdrop:backdrop-blur-md',
        'open:animate-in open:fade-in open:zoom-in-95',
        adaptive && 'os-modal-light',
        className
      )}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
    >
      <div className="p-5 sm:p-6">
        {title && (
          <div className="mb-5 flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        {children}
      </div>
    </dialog>
  );
}
