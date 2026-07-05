import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useTenantStatus } from '@/hooks/useTenantStatus';
import { btcpayPayoutProcessorsUrl, btcpayPayoutsUrl } from '@/lib/payments';
import { statusStripItems, type StatusStripItem, type StatusTone } from '@/lib/statusStrip';
import { cn } from '@/lib/utils';

const TONE_DOT: Record<StatusTone, string> = {
  ok: 'bg-emerald-400',
  warn: 'bg-amber-300',
  bad: 'bg-red-400',
  idle: 'bg-white/25',
};

const ITEM_CLASS =
  'group inline-flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-[#C7CEDA] transition-colors hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-[#F5F5F7]';

function Dot({ tone }: { tone: StatusTone }) {
  return <span className={cn('h-2 w-2 shrink-0 rounded-full', TONE_DOT[tone])} aria-hidden />;
}

function ItemShell({ item, children }: { item: StatusStripItem; children: ReactNode }) {
  // Deep-link priority: internal SPA route, then external BTCPay link, then a
  // same-page scroll anchor. Falls back to a plain, non-interactive chip.
  const title = item.hint;
  if (item.to) {
    return (
      <Link to={item.to} className={ITEM_CLASS} title={title}>
        {children}
      </Link>
    );
  }
  if (item.href) {
    return (
      <a href={item.href} target="_blank" rel="noreferrer" className={ITEM_CLASS} title={title}>
        {children}
      </a>
    );
  }
  if (item.anchor) {
    return (
      <a href={`#${item.anchor}`} className={ITEM_CLASS} title={title}>
        {children}
      </a>
    );
  }
  return (
    <span className={cn(ITEM_CLASS, 'cursor-default')} title={title}>
      {children}
    </span>
  );
}

/** Compact horizontal pipeline-health strip for the Team page. Five checks —
 *  store, webhook, active rule, payout delivery, public page — each a coloured
 *  dot + short label that deep-links to its fix. Self-updating (~30s poll). */
export function StatusStrip() {
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
  const guidance = items.find((item) => item.guidance)?.guidance;

  return (
    <div className="flex flex-col gap-2">
      <nav
        aria-label="Pipeline status"
        className="flex flex-wrap items-center gap-2 rounded-xl border border-white/[0.07] bg-[#11131F]/48 p-2.5"
      >
        {items.map((item) => (
          <ItemShell key={item.key} item={item}>
            <Dot tone={item.tone} />
            <span className="max-w-[200px] truncate">{item.label}</span>
          </ItemShell>
        ))}
      </nav>
      {guidance && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2.5 text-sm text-[#C7CEDA]">
          <span className="flex-1">{guidance.text}</span>
          <a
            href={guidance.fixHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-1.5 font-medium text-amber-200 transition-colors hover:bg-amber-300/20"
          >
            {guidance.fixLabel}
          </a>
        </div>
      )}
    </div>
  );
}
