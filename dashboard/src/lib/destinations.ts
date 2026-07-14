/** Destination badges for split targets (PR 4, P-3).
 *
 * Pure, data-derived helpers: they classify where a target's payout will go
 * from existing API fields and flag addresses that look like a plain email
 * rather than a Lightning address. Warning-only — never blocks a rule.
 */

import i18n from '@/i18n';

export type DestinationKind = 'lightning-address' | 'lnd-receiver' | 'none';

export interface DestinationBadge {
  kind: DestinationKind;
  label: string;
  /** Maps to the shared Badge variants. */
  variant: 'success' | 'default';
}

export interface TargetDestinationInput {
  ln_address?: string | null;
  has_lnd_receiver?: boolean;
}

/** Domains that are email providers, not Lightning-address hosts. A target
 *  pointed at one of these will never receive a payout. */
const EMAIL_PROVIDER_DOMAINS = new Set([
  'gmail.com',
  'outlook.com',
  'hotmail.com',
  'yahoo.com',
  'icloud.com',
]);

/** True when `lnAddress`'s domain is a known consumer email provider. */
export function looksLikeEmailProvider(lnAddress: string | null | undefined): boolean {
  if (!lnAddress) return false;
  const trimmed = lnAddress.trim().toLowerCase();
  const at = trimmed.lastIndexOf('@');
  if (at < 0) return false;
  const domain = trimmed.slice(at + 1);
  return EMAIL_PROVIDER_DOMAINS.has(domain);
}

/** Classify a target's payout destination for the at-a-glance badge. An LND
 *  receiver takes precedence (it mints its own invoice, no address needed);
 *  otherwise a present Lightning address; otherwise nothing configured. */
export function destinationBadge(target: TargetDestinationInput): DestinationBadge {
  if (target.has_lnd_receiver) {
    return { kind: 'lnd-receiver', label: i18n.t('splits.destination.lndReceiver'), variant: 'success' };
  }
  if (target.ln_address && target.ln_address.trim()) {
    return { kind: 'lightning-address', label: i18n.t('splits.destination.lightningAddress'), variant: 'success' };
  }
  return { kind: 'none', label: i18n.t('splits.destination.none'), variant: 'default' };
}
