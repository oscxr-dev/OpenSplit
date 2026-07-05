import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useTenantStatus } from '@/hooks/useTenantStatus';
import { btcpayPayoutProcessorsUrl, btcpayPayoutsUrl } from '@/lib/payments';
import {
  statusStripItems,
  summarizeStatus,
  type StatusSummaryTone,
} from '@/lib/statusStrip';
import { cn } from '@/lib/utils';

// Tone treatment mirrors the shared Badge variants so the pill matches the
// success/warning/error chips used across the app — and, like them, renders
// correctly in both light and dark themes (semantic emerald/amber/red tints).
const TONE_SHELL: Record<StatusSummaryTone, string> = {
  ok: 'border-emerald-300/15 bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15',
  warn: 'border-amber-300/15 bg-amber-400/10 text-amber-200 hover:bg-amber-400/15',
  bad: 'border-red-300/15 bg-red-400/10 text-red-300 hover:bg-red-400/15',
};

const TONE_DOT: Record<StatusSummaryTone, string> = {
  ok: 'bg-emerald-400',
  warn: 'bg-amber-300',
  bad: 'bg-red-400',
};

/** One-line worst-state summary of the five pipeline checks for the Team page.
 *  Rolls statusStripItems() into a single pill (via summarizeStatus) that deep-
 *  links to the full detail strip in Settings › Connection. Renders nothing
 *  until status has loaded, matching the detail strip's no-data behavior. */
export function StatusSummaryPill() {
  const { tenant } = useAuth();
  const { data: status } = useTenantStatus();

  if (!status) return null;

  const payoutsUrl = btcpayPayoutsUrl(
    tenant?.tenant.btcpay_url,
    tenant?.tenant.btcpay_store_id,
    window.location.hostname
  );
  const payoutProcessorsUrl = btcpayPayoutProcessorsUrl(
    tenant?.tenant.btcpay_url,
    tenant?.tenant.btcpay_store_id,
    window.location.hostname
  );
  const items = statusStripItems(status, { payoutsUrl, payoutProcessorsUrl });
  const summary = summarizeStatus(items);

  return (
    <Link
      to="/settings#connection"
      aria-label={`Pipeline status: ${summary.label}. Open connection settings.`}
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
        TONE_SHELL[summary.tone]
      )}
    >
      <span className={cn('h-2 w-2 shrink-0 rounded-full', TONE_DOT[summary.tone])} aria-hidden />
      <span className="max-w-[280px] truncate">{summary.label}</span>
    </Link>
  );
}
