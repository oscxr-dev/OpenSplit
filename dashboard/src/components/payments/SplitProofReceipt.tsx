import { AlertCircle, CheckCircle, Clock, Copy, ExternalLink, KeyRound, Radio, ReceiptText, RotateCcw, ShieldCheck, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { usePublishProof, useProof, useSignProof } from '@/hooks/useProof';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { cn, copyToClipboard, formatDate, formatSats, payoutStatusLabel } from '@/lib/utils';
import { btcpayPayoutsUrl, isWaitingInBtcpay } from '@/lib/payments';
import { proofPermalink } from '@/lib/browserUrl';
import { proofBalanceLabel, truncateMiddle } from '@/lib/transparency';
import type { Invoice, PaymentSplit } from '@/types/api';

interface SplitProofReceiptProps {
  payment: Invoice;
  onRetrySplit?: (split: PaymentSplit) => void;
  retrying?: boolean;
}

/** Lightning settlement proof for one completed payout: the preimage BTCPay
 *  recorded when the payment settled (sha256(preimage) equals the payment
 *  hash). Shown only for completed splits that have one — it is evidence the
 *  payout settled on the Lightning Network, not a DB-internal check. */
function LightningSettlementProof({ preimage, paymentHash }: { preimage: string; paymentHash: string | null }) {
  const { t } = useTranslation();

  function handleCopyPreimage() {
    copyToClipboard(preimage)
      .then(() => toast.success(t('proof.preimageCopied')))
      .catch(() => toast.error(t('proof.preimageCopyError')));
  }

  return (
    <div className="mt-2.5 rounded border border-white/[0.07] bg-[#0A0B12]/42 px-2.5 py-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5 font-medium text-[#F5F5F7]">
          <Zap className="h-3.5 w-3.5 shrink-0 text-[#FF2D78]" strokeWidth={1.8} />
          {t('proof.lightningSettlementProof')}
        </span>
        <button
          type="button"
          onClick={handleCopyPreimage}
          className="inline-flex shrink-0 items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6]"
        >
          <Copy className="h-3 w-3" strokeWidth={1.8} />
          {t('proof.copyPreimage')}
        </button>
      </div>
      <p
        className="mt-1.5 truncate font-mono text-[#94A3B8]"
        title={t('proof.preimageTitle')}
      >
        {t('proof.preimageValue', { value: truncateMiddle(preimage, 18, 10) })}
      </p>
      {paymentHash && (
        <p className="mt-0.5 truncate font-mono text-[#94A3B8]">{t('proof.hashValue', { value: truncateMiddle(paymentHash, 18, 10) })}</p>
      )}
    </div>
  );
}

export function SplitProofReceipt({ payment, onRetrySplit, retrying = false }: SplitProofReceiptProps) {
  const { t } = useTranslation();
  const { data: proof, isLoading, isError, refetch } = useProof(payment.id);
  const { tenant } = useAuth();
  const signProof = useSignProof(payment.id);
  // "Sign proof" only makes sense once the payment is fully paid (the split
  // set is final) and the team has a Nostr public key configured. The signing
  // key itself lives on the server (env), never in the browser.
  const nostrProof = proof?.nostr_proof ?? null;
  const canSign = !nostrProof && payment.status === 'paid' && Boolean(tenant?.tenant.nostr_pubkey);
  // Relay publication only exists for a signed proof; the backend publishes
  // best-effort on sign and this button retries it (flaky/new relays).
  const publishProof = usePublishProof(payment.id);
  const relayResults = nostrProof?.relay_results ?? null;
  const acceptedRelays = relayResults?.filter((result) => result.ok).length ?? 0;

  function handlePublishProof() {
    publishProof.mutate(undefined, {
      onSuccess: (published) => {
        const results = published.relay_results ?? [];
        const accepted = results.filter((result) => result.ok).length;
        if (accepted > 0) {
          toast.success(t('proof.publishSuccessToast', { accepted, count: results.length }));
        } else {
          toast.error(t('proof.publishNoneToast'));
        }
      },
      onError: (error) => {
        const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
          ?.detail;
        toast.error(typeof detail === 'string' ? detail : t('proof.publishError'));
      },
    });
  }

  function handleSignProof() {
    signProof.mutate(undefined, {
      onSuccess: () => toast.success(t('proof.signSuccess')),
      onError: (error) => {
        const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
          ?.detail;
        toast.error(typeof detail === 'string' ? detail : t('proof.signError'));
      },
    });
  }

  function handleCopyNostrEvent() {
    if (!nostrProof) return;
    copyToClipboard(nostrProof.event_json)
      .then(() => toast.success(t('proof.eventCopied')))
      .catch(() => toast.error(t('proof.eventCopyError')));
  }
  const payoutsUrl = btcpayPayoutsUrl(
    tenant?.tenant.btcpay_url,
    tenant?.tenant.btcpay_store_id,
    window.location.hostname
  );
  // Shareable app permalink to this proof (authenticated PageProof route) —
  // the receipt footer shows this instead of the raw /payments API path.
  const proofLink = proofPermalink(window.location.origin, payment.id);

  function handleCopyProofLink() {
    copyToClipboard(proofLink)
      .then(() => toast.success(t('proof.proofLinkCopied')))
      .catch(() => toast.error(t('proof.proofLinkCopyError')));
  }

  function handleCopyFingerprint() {
    if (!proof?.rule_fingerprint) return;
    copyToClipboard(proof.rule_fingerprint)
      .then(() => toast.success(t('proof.fingerprintCopied')))
      .catch(() => toast.error(t('proof.fingerprintCopyError')));
  }

  const proofRows = proof?.members.map((member) => {
    const matchingSplit = payment.splits.find((split) => split.id === member.split_id);
    return {
      id: member.split_id,
      label: member.label || matchingSplit?.label || t('proof.unnamedPartner'),
      identity: member.nostr_pubkey || matchingSplit?.ln_address || member.ln_address,
      percentage: member.percentage,
      amountSats: member.amount_sats,
      status: member.payout_status,
      rawState: member.btcpay_payout_state ?? matchingSplit?.btcpay_payout_state ?? null,
      preimage: member.ln_preimage ?? matchingSplit?.ln_preimage ?? null,
      paymentHash: member.ln_payment_hash ?? matchingSplit?.ln_payment_hash ?? null,
      retrySplit: matchingSplit,
    };
  }) ?? payment.splits.map((split) => ({
    id: split.id,
    label: split.label || t('proof.unnamedPartner'),
    identity: split.ln_address,
    percentage: null,
    amountSats: split.amount_sats,
    status: split.status,
    rawState: split.btcpay_payout_state ?? null,
    preimage: split.ln_preimage ?? null,
    paymentHash: split.ln_payment_hash ?? null,
    retrySplit: split,
  }));

  return (
    <article className="split-proof-receipt overflow-hidden rounded-lg border border-[#FF2D78]/18 bg-[#11131F]">
      <header className="border-b border-white/[0.08] bg-white/[0.025] p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
              <h2 className="text-xl font-semibold text-[#F5F5F7]">{t('proof.title')}</h2>
            </div>
            <p className="mt-2 text-sm text-[#94A3B8]">{t('proof.subtitle')}</p>
          </div>
          <p className="font-mono text-xs font-semibold text-[#FF2D78]">
            {proof ? proofBalanceLabel(proof.integrity.balanced) : t('proof.loadingProof')}
          </p>
        </div>
      </header>

      <div className="grid gap-4 p-5 sm:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">{t('proof.amount')}</p>
          <p className="mt-2 font-mono text-2xl font-semibold text-[#F5F5F7]">{formatSats(payment.amount_sats)}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">{t('proof.rule')}</p>
          <p className="mt-2 font-mono text-lg font-semibold text-[#F5F5F7]">
            {proof?.split_rule_version != null ? t('proof.ruleSealed', { version: proof.split_rule_version }) : t('proof.pending')}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">{t('proof.paidLabel')}</p>
          <p className="mt-2 font-mono text-sm text-[#F5F5F7]">{formatDate(payment.paid_at || payment.created_at)}</p>
        </div>
      </div>

      <div className="border-y border-white/[0.08] px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#F5F5F7]">
          <ReceiptText className="h-4 w-4 text-[#FF2D78]" strokeWidth={1.8} />
          {t('proof.teamShares')}
        </div>

        {isLoading && <Skeleton className="mt-4 h-28 w-full" />}

        {isError && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-red-300/15 bg-red-400/[0.08] p-3 text-sm text-red-300">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" strokeWidth={1.8} />
              {t('proof.loadError')}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={() => refetch()}>
              {t('common.retry')}
            </Button>
          </div>
        )}

        <div className="mt-4 space-y-2">
          {proofRows.map((row) => {
            const waiting = isWaitingInBtcpay({ status: row.status, btcpay_payout_state: row.rawState });
            return (
              <div key={row.id} className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
                <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="font-medium text-[#F5F5F7]">{row.label}</p>
                    <p className="mt-1 truncate font-mono text-xs text-[#94A3B8]">
                      {row.identity ? truncateMiddle(row.identity) : t('proof.noPublicIdentity')}
                    </p>
                  </div>
                  <p className="font-mono text-sm font-semibold text-[#F5F5F7]">
                    {row.percentage != null ? `${row.percentage}%` : '—'}
                  </p>
                  <div className="flex items-center justify-between gap-3 sm:justify-end">
                    <div className="text-right">
                      <p className="font-mono text-sm font-semibold text-[#F5F5F7]">{formatSats(row.amountSats)}</p>
                      <p className={cn('mt-1 text-xs', waiting ? 'text-amber-200' : 'text-[#94A3B8]')}>
                        {waiting ? t('payments.waitingInBtcpay') : payoutStatusLabel(row.status)}
                      </p>
                    </div>
                    {row.status === 'failed' && row.retrySplit && onRetrySplit && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        loading={retrying}
                        onClick={() => onRetrySplit(row.retrySplit!)}
                        aria-label={t('proof.retryPayoutAria', { label: row.label })}
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>

                {row.status === 'completed' && row.preimage && (
                  <LightningSettlementProof preimage={row.preimage} paymentHash={row.paymentHash} />
                )}

                {waiting && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded border border-amber-300/15 bg-amber-400/[0.08] px-2.5 py-1.5 text-xs text-amber-200">
                    <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
                    <span>{t('payments.waitingHint')}.</span>
                    {payoutsUrl && (
                      <a
                        href={payoutsUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-medium underline underline-offset-2 hover:text-amber-100"
                      >
                        {t('proof.openInBtcpay')}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <footer className="space-y-3 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#F5F5F7]">
          <CheckCircle className="h-4 w-4 text-[#FF2D78]" strokeWidth={1.8} />
          {t('proof.integrity')}
        </div>
        <div className="grid gap-3 text-xs sm:grid-cols-2">
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
            <p className="text-[#94A3B8]">{t('proof.paymentId')}</p>
            <p className="mt-1 truncate font-mono text-[#F5F5F7]">{payment.id}</p>
          </div>
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[#94A3B8]">{t('proof.proofLink')}</p>
              <button
                type="button"
                onClick={handleCopyProofLink}
                className="inline-flex shrink-0 items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6]"
              >
                <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
                {t('proof.copyProofLink')}
              </button>
            </div>
            <p className="mt-1 truncate font-mono text-[#F5F5F7]">{proofLink}</p>
          </div>
          {proof?.rule_fingerprint && (
            <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3 sm:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <p
                  className="text-[#94A3B8]"
                  title={t('proof.fingerprintTitle')}
                >
                  {t('proof.ruleFingerprint')}
                </p>
                <button
                  type="button"
                  onClick={handleCopyFingerprint}
                  className="inline-flex shrink-0 items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6]"
                >
                  <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
                  {t('proof.copyFingerprint')}
                </button>
              </div>
              <p className="mt-1 truncate font-mono text-[#F5F5F7]">
                {truncateMiddle(proof.rule_fingerprint, 18, 10)}
              </p>
            </div>
          )}
          {nostrProof && (
            <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3 sm:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <p className="flex items-center gap-1.5 text-[#94A3B8]">
                  <KeyRound className="h-3.5 w-3.5 shrink-0 text-[#FF2D78]" strokeWidth={1.8} />
                  {t('proof.nostrSignature')}
                </p>
                <button
                  type="button"
                  onClick={handleCopyNostrEvent}
                  className="inline-flex shrink-0 items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6]"
                >
                  <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
                  {t('proof.copyEventJson')}
                </button>
              </div>
              <p className="mt-1.5 text-[#94A3B8]">
                {t('proof.signedWithKey')}
              </p>
              <p
                className="mt-1.5 truncate font-mono text-[#F5F5F7]"
                title={t('proof.eventIdTitle')}
              >
                {t('proof.eventValue', { value: truncateMiddle(nostrProof.event_id, 18, 10) })}
              </p>
              <p className="mt-0.5 truncate font-mono text-[#94A3B8]" title={nostrProof.npub}>
                {t('proof.verifiesAgainst', { value: truncateMiddle(nostrProof.npub, 14, 8) })}
              </p>

              <div className="mt-2.5 border-t border-white/[0.08] pt-2.5">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                  <p className="flex items-center gap-1.5 text-[#94A3B8]">
                    <Radio className="h-3.5 w-3.5 shrink-0 text-[#FF2D78]" strokeWidth={1.8} />
                    {t('proof.relayPublication')}
                  </p>
                  <button
                    type="button"
                    disabled={publishProof.isPending}
                    onClick={handlePublishProof}
                    className="inline-flex shrink-0 items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6] disabled:pointer-events-none disabled:opacity-40"
                  >
                    <Radio className="h-3.5 w-3.5" strokeWidth={1.8} />
                    {publishProof.isPending
                      ? t('proof.publishing')
                      : relayResults
                        ? t('proof.republishToRelays')
                        : t('proof.publishToRelays')}
                  </button>
                </div>
                {relayResults ? (
                  <>
                    <p className="mt-1.5 text-[#94A3B8]">
                      {acceptedRelays > 0
                        ? t('proof.acceptedByRelays', { accepted: acceptedRelays, count: relayResults.length })
                        : t('proof.noRelayAccepted')}
                    </p>
                    <ul className="mt-1.5 space-y-1">
                      {relayResults.map((result) => (
                        <li key={result.relay} className="flex items-start gap-1.5 font-mono text-xs">
                          {result.ok ? (
                            <CheckCircle className="mt-px h-3.5 w-3.5 shrink-0 text-emerald-300" strokeWidth={1.8} />
                          ) : (
                            <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0 text-red-300" strokeWidth={1.8} />
                          )}
                          <span className="min-w-0">
                            <span className={cn('break-all', result.ok ? 'text-[#F5F5F7]' : 'text-red-300')}>
                              {result.relay.replace(/^wss?:\/\//, '')}
                            </span>
                            {!result.ok && result.error && (
                              <span className="block text-red-300/80">{result.error}</span>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="mt-1.5 text-[#94A3B8]">
                    {t('proof.notPublishedYet')}
                  </p>
                )}
                {acceptedRelays > 0 && (
                  <a
                    href={`https://njump.me/${nostrProof.note_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1.5 inline-flex items-center gap-1 font-medium text-[#FF2D78] transition-colors hover:text-[#FF6DA6]"
                    title={nostrProof.note_id}
                  >
                    {t('proof.lookupNjump')}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
            </div>
          )}
          {canSign && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3 sm:col-span-2">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-[#94A3B8]">
                  <KeyRound className="h-3.5 w-3.5 shrink-0 text-[#FF2D78]" strokeWidth={1.8} />
                  {t('proof.nostrSignature')}
                </p>
                <p className="mt-1.5 text-[#94A3B8]">
                  {t('proof.sealPrompt')}
                </p>
              </div>
              <Button
                type="button"
                variant="primary"
                size="sm"
                loading={signProof.isPending}
                onClick={handleSignProof}
              >
                {t('proof.signProof')}
              </Button>
            </div>
          )}
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3 sm:col-span-2">
            <p className="text-[#94A3B8]">{t('proof.balance')}</p>
            <p className="mt-1 font-mono text-[#F5F5F7]">
              {proof
                ? `${formatSats(proof.integrity.split_sum_sats)} / ${formatSats(proof.integrity.payment_amount_sats)}`
                : t('proof.waitingForProof')}
            </p>
          </div>
        </div>
      </footer>
    </article>
  );
}
