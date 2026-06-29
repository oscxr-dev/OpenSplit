import { describe, expect, it } from 'vitest';
import { splitRuleSchema } from './split';

function target(percentage: number, i = 0) {
  return { label: `P${i}`, ln_address: `p${i}@wallet.com`, percentage, order: i };
}

describe('splitRuleSchema — partial allocation', () => {
  it('accepts a partial rule totalling under 100%', () => {
    const result = splitRuleSchema.safeParse({
      name: 'Partial',
      targets: [target(20, 0), target(20, 1), target(20, 2)], // 60%
    });
    expect(result.success).toBe(true);
  });

  it('accepts a rule totalling exactly 100%', () => {
    const result = splitRuleSchema.safeParse({
      name: 'Full',
      targets: [target(60, 0), target(40, 1)],
    });
    expect(result.success).toBe(true);
  });

  it('rejects a rule totalling over 100%', () => {
    const result = splitRuleSchema.safeParse({
      name: 'Over',
      targets: [target(60, 0), target(60, 1)], // 120%
    });
    expect(result.success).toBe(false);
  });
});
