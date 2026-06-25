import { describe, expect, it } from 'vitest';
import { memberPayoutHealth, proofBalanceLabel, truncateMiddle } from './transparency';

describe('truncateMiddle', () => {
  it('leaves short values untouched', () => {
    expect(truncateMiddle('npub1abc')).toBe('npub1abc');
  });

  it('collapses long values keeping head and tail', () => {
    const npub = 'npub1m8sk4qwer7tyuiopasdfghjklzxcvbnmt92hv';
    const out = truncateMiddle(npub);
    expect(out.startsWith('npub1m8sk4')).toBe(true);
    expect(out.endsWith('t92hv')).toBe(true);
    expect(out).toContain('…');
    expect(out.length).toBeLessThan(npub.length);
  });

  it('honors custom lead/tail', () => {
    expect(truncateMiddle('abcdefghijklmnop', 4, 4)).toBe('abcd…mnop');
  });
});

describe('memberPayoutHealth', () => {
  it('is healthy with zero failures', () => {
    expect(memberPayoutHealth(0)).toBe('healthy');
  });

  it('is failed with any failures', () => {
    expect(memberPayoutHealth(1)).toBe('failed');
    expect(memberPayoutHealth(7)).toBe('failed');
  });
});

describe('proofBalanceLabel', () => {
  it('maps balance to a label', () => {
    expect(proofBalanceLabel(true)).toBe('Balance verified');
    expect(proofBalanceLabel(false)).toBe('Mismatch detected');
  });
});
