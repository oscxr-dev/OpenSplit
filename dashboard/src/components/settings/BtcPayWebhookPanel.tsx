import { useEffect, useState } from 'react';
import axios from 'axios';
import { formatDistanceToNow, parseISO } from 'date-fns';
import { AlertTriangle, Copy, RefreshCw, Webhook } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useAuth } from '@/hooks/useAuth';
import api from '@/lib/api';
import { copyToClipboard } from '@/lib/utils';
import type { BtcPayWebhookSecret } from '@/types/api';

/** How often the tenant is re-fetched while waiting for BTCPay's first
 *  signature-valid delivery to flip the panel to "verified". */
const VERIFY_POLL_MS = 10_000;

function apiErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Hosts only reachable from the operator's own machine/Docker host. The
 *  webhook URL is SERVER-perspective (BTCPay calls it from its own network),
 *  so it is deliberately NOT rewritten with browserUrl.ts — we only hint. */
function isLocalOnlyHost(url: string): boolean {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === 'host.docker.internal'
    );
  } catch {
    return false;
  }
}

function lastEventLabel(lastWebhookAt: string): string {
  try {
    return formatDistanceToNow(parseISO(lastWebhookAt), { addSuffix: true });
  } catch {
    return 'recently';
  }
}

function CopyButton({ value, label }: { value: string; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => {
        copyToClipboard(value)
          .then(() => toast.success('Copied to clipboard'))
          .catch(() => toast.error('Could not copy — copy it manually'));
      }}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.12] text-[#94A3B8] transition hover:border-[#FF2D78]/45 hover:text-[#FF2D78] focus:outline-none focus:ring-2 focus:ring-[#FF2D78]/20"
    >
      <Copy className="h-3.5 w-3.5" strokeWidth={2} />
    </button>
  );
}

export function BtcPayWebhookPanel() {
  const { tenant, refreshTenant } = useAuth();
  const info = tenant?.tenant;
  const secretSet = Boolean(info?.btcpay_webhook_secret_set);
  const lastWebhookAt = info?.last_webhook_at ?? null;
  const verified = secretSet && Boolean(lastWebhookAt);

  // One-time reveal of a freshly generated secret. Lives only in this state:
  // once dismissed (or on unmount) the secret is unrecoverable by design.
  const [reveal, setReveal] = useState<BtcPayWebhookSecret | null>(null);
  const [generating, setGenerating] = useState(false);
  const [confirmRegenerateOpen, setConfirmRegenerateOpen] = useState(false);
  // True once this session regenerated: BTCPay still signs with the OLD
  // secret until the operator updates it there, so warn until re-verified.
  const [regenerated, setRegenerated] = useState(false);

  // Poll while the panel is visible and a secret is configured, so "waiting"
  // flips to "verified" on its own and the relative time stays fresh.
  useEffect(() => {
    if (!secretSet) return;
    const id = setInterval(() => {
      void refreshTenant();
    }, VERIFY_POLL_MS);
    return () => clearInterval(id);
  }, [secretSet, refreshTenant]);

  async function generateSecret() {
    setGenerating(true);
    try {
      const res = await api.post<BtcPayWebhookSecret>('/tenants/me/btcpay/webhook-secret');
      if (secretSet) setRegenerated(true);
      setReveal(res.data);
      await refreshTenant();
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Could not generate the webhook secret'));
    } finally {
      setGenerating(false);
      setConfirmRegenerateOpen(false);
    }
  }

  const statusBadge = verified ? 'Verified' : secretSet ? 'Waiting' : 'Not configured';

  return (
    <div className="p-6 sm:p-8">
      <div className="flex flex-wrap items-center gap-3">
        <Webhook className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
        <h2 className="font-semibold text-[#F5F5F7]">Webhook</h2>
        <Badge variant={verified ? 'success' : secretSet ? 'warning' : 'default'}>
          {statusBadge}
        </Badge>
      </div>
      <p className="mt-2 text-sm text-[#94A3B8]">
        BTCPay pushes settled invoices to OpenSplit through a signed webhook. Events without a
        valid signature are rejected.
      </p>

      {!secretSet && !reveal && (
        <div className="mt-4 rounded-2xl border border-white/[0.10] bg-white/[0.03] px-4 py-3 text-sm text-[#94A3B8]">
          <span className="font-semibold text-[#F5F5F7]">No webhook secret yet.</span> Splits only
          run once BTCPay can deliver signed events. Generate a secret here, then create the
          webhook in BTCPay with it — the guided steps appear after generating.
        </div>
      )}

      {reveal && (
        <div className="mt-5 rounded-2xl border border-white/[0.10] bg-white/[0.03] p-4 sm:p-5">
          <p className="text-sm font-semibold text-[#F5F5F7]">
            Create the webhook in BTCPay (Store settings → Webhooks → Create Webhook):
          </p>
          <ol className="mt-4 space-y-4">
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#FF2D78]/14 text-xs font-bold text-[#FF2D78]">
                1
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#F5F5F7]">Paste this as the Payload URL</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg border border-white/[0.10] bg-[#11131F] px-3 py-2 font-mono text-xs text-[#F5F5F7]">
                    {reveal.webhook_url}
                  </code>
                  <CopyButton value={reveal.webhook_url} label="Copy webhook URL" />
                </div>
                {isLocalOnlyHost(reveal.webhook_url) && (
                  <p className="mt-2 text-xs text-[#94A3B8]">
                    This is the address BTCPay must reach — it is served from BTCPay&apos;s own
                    network, not your browser.
                  </p>
                )}
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#FF2D78]/14 text-xs font-bold text-[#FF2D78]">
                2
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#F5F5F7]">Paste this as the Secret</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg border border-white/[0.10] bg-[#11131F] px-3 py-2 font-mono text-xs text-[#F5F5F7]">
                    {reveal.secret}
                  </code>
                  <CopyButton value={reveal.secret} label="Copy webhook secret" />
                </div>
                <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-amber-200">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                  Shown only once — paste it into BTCPay now.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#FF2D78]/14 text-xs font-bold text-[#FF2D78]">
                3
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#F5F5F7]">
                  Under events, choose “Send specific events” and tick:
                </p>
                <ul className="mt-2 space-y-1">
                  {reveal.events.map((event) => (
                    <li key={event} className="font-mono text-xs text-[#F5F5F7]">
                      • {event}
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          </ol>
          <div className="mt-5 flex justify-end">
            <Button variant="outline" size="sm" onClick={() => setReveal(null)}>
              Done — I saved it in BTCPay
            </Button>
          </div>
        </div>
      )}

      {regenerated && !verified && (
        <div className="mt-4 flex items-start gap-2.5 rounded-2xl border border-amber-300/20 bg-amber-400/[0.08] px-4 py-3 text-sm font-medium text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2} />
          <span>Update the secret in BTCPay — old events will be rejected.</span>
        </div>
      )}

      {secretSet && (
        <div className="mt-4 flex items-center gap-2.5 text-sm" role="status">
          {verified ? (
            <>
              <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
              <span className="font-medium text-emerald-300">
                Webhook verified — last event {lastEventLabel(lastWebhookAt as string)}
              </span>
            </>
          ) : (
            <>
              <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-amber-300" />
              <span className="font-medium text-amber-200">Waiting for first webhook…</span>
            </>
          )}
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {!secretSet ? (
          <Button variant="primary" size="sm" onClick={generateSecret} loading={generating}>
            Generate webhook secret
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirmRegenerateOpen(true)}
            disabled={generating}
          >
            <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
            Regenerate secret
          </Button>
        )}
      </div>

      <ConfirmDialog
        open={confirmRegenerateOpen}
        title="Regenerate webhook secret?"
        description="The current secret stops working immediately. BTCPay keeps signing with the old one until you paste the new secret there, so deliveries will be rejected in the meantime."
        cancelLabel="Cancel"
        confirmLabel="Regenerate"
        destructive
        loading={generating}
        confirmDisabled={generating}
        onClose={() => setConfirmRegenerateOpen(false)}
        onConfirm={() => {
          void generateSecret();
        }}
      />
    </div>
  );
}
