import type { SplitRule } from '@/types/api';

export type RuleLibraryFilter = 'all' | 'active' | 'inactive';

/**
 * Filter the Rule Library by free-text name search and an active/inactive
 * status filter. Pure + side-effect free so it can be unit tested directly.
 */
export function filterRules(
  rules: SplitRule[],
  search: string,
  filter: RuleLibraryFilter
): SplitRule[] {
  const query = search.trim().toLowerCase();
  return rules.filter((rule) => {
    if (filter === 'active' && !rule.active) return false;
    if (filter === 'inactive' && rule.active) return false;
    if (query && !rule.name.toLowerCase().includes(query)) return false;
    return true;
  });
}
