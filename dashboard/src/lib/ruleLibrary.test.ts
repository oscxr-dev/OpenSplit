import { describe, expect, it } from 'vitest';
import { filterRules } from './ruleLibrary';
import type { SplitRule } from '@/types/api';

function rule(partial: Partial<SplitRule> & { id: string; name: string; active: boolean }): SplitRule {
  return {
    version: 1,
    parent_rule_id: null,
    targets: [],
    created_at: '2025-01-01T00:00:00Z',
    can_delete: true,
    ...partial,
  } as SplitRule;
}

const rules: SplitRule[] = [
  rule({ id: '1', name: 'Barista Split', active: true }),
  rule({ id: '2', name: 'Holiday Promo', active: false }),
  rule({ id: '3', name: 'Reserve Fund', active: true }),
  rule({ id: '4', name: 'Old Barista Draft', active: false }),
];

describe('filterRules', () => {
  it('returns everything with the "all" filter and no search', () => {
    expect(filterRules(rules, '', 'all')).toHaveLength(4);
  });

  it('keeps only active rules', () => {
    const result = filterRules(rules, '', 'active');
    expect(result.map((r) => r.id)).toEqual(['1', '3']);
  });

  it('keeps only inactive rules', () => {
    const result = filterRules(rules, '', 'inactive');
    expect(result.map((r) => r.id)).toEqual(['2', '4']);
  });

  it('searches by name case-insensitively', () => {
    const result = filterRules(rules, 'barista', 'all');
    expect(result.map((r) => r.id)).toEqual(['1', '4']);
  });

  it('combines search with the status filter', () => {
    const result = filterRules(rules, 'barista', 'inactive');
    expect(result.map((r) => r.id)).toEqual(['4']);
  });

  it('ignores surrounding whitespace in the query', () => {
    expect(filterRules(rules, '  reserve  ', 'all').map((r) => r.id)).toEqual(['3']);
  });

  it('returns nothing when no rule matches', () => {
    expect(filterRules(rules, 'nonexistent', 'all')).toHaveLength(0);
  });
});
