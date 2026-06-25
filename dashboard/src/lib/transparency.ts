/** Pure presentation helpers for members / proof / public transparency. */

/** Shorten a long identifier (npub, hash) keeping head and tail readable. */
export function truncateMiddle(value: string, lead = 10, tail = 6): string {
  if (value.length <= lead + tail + 1) return value;
  return `${value.slice(0, lead)}…${value.slice(-tail)}`;
}

/** Derive a coarse payout health for a member from its failed payout count. */
export function memberPayoutHealth(failedCount: number): 'failed' | 'healthy' {
  return failedCount > 0 ? 'failed' : 'healthy';
}

/** Human label for the proof integrity check. */
export function proofBalanceLabel(balanced: boolean): string {
  return balanced ? 'Balance verified' : 'Mismatch detected';
}
