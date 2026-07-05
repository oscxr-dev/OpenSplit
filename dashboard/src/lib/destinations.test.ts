import { describe, expect, it } from 'vitest';
import { destinationBadge, looksLikeEmailProvider } from './destinations';

describe('destinationBadge', () => {
  it('prefers the local LND receiver when configured', () => {
    const badge = destinationBadge({ has_lnd_receiver: true, ln_address: 'x@wallet.com' });
    expect(badge.kind).toBe('lnd-receiver');
    expect(badge.label).toBe('Local LND receiver');
    expect(badge.variant).toBe('success');
  });

  it('reports a Lightning address when one is present', () => {
    const badge = destinationBadge({ ln_address: 'barista@walletofsatoshi.com' });
    expect(badge.kind).toBe('lightning-address');
    expect(badge.label).toBe('Lightning address');
  });

  it('flags a target with no destination', () => {
    expect(destinationBadge({}).kind).toBe('none');
    expect(destinationBadge({ ln_address: '  ' }).kind).toBe('none');
    expect(destinationBadge({}).label).toBe('No destination');
  });

  it('still reports Lightning address for an email-looking address (caution is separate)', () => {
    // The badge is presence-derived; the email caution is a separate signal.
    expect(destinationBadge({ ln_address: 'someone@gmail.com' }).kind).toBe('lightning-address');
  });
});

describe('looksLikeEmailProvider', () => {
  it('matches known consumer email providers, case-insensitively', () => {
    for (const addr of [
      'someone@gmail.com',
      'a@outlook.com',
      'b@hotmail.com',
      'c@yahoo.com',
      'd@icloud.com',
      'MixedCase@Gmail.com',
    ]) {
      expect(looksLikeEmailProvider(addr)).toBe(true);
    }
  });

  it('does not flag real Lightning-address hosts', () => {
    expect(looksLikeEmailProvider('barista@walletofsatoshi.com')).toBe(false);
    expect(looksLikeEmailProvider('me@getalby.com')).toBe(false);
  });

  it('handles empty / malformed input', () => {
    expect(looksLikeEmailProvider(null)).toBe(false);
    expect(looksLikeEmailProvider(undefined)).toBe(false);
    expect(looksLikeEmailProvider('no-at-sign')).toBe(false);
    expect(looksLikeEmailProvider('')).toBe(false);
  });
});
