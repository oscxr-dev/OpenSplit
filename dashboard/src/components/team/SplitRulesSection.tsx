import { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import { Archive, GitBranch, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useActivateSplit, useCreateSplit, useDeleteSplit, useUpdateSplit } from '@/hooks/useSplits';
import { SplitBar } from '@/components/splits/SplitBar';
import { SplitRuleForm } from '@/components/splits/SplitRuleForm';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/shared/ErrorState';
import { formatDate } from '@/lib/utils';
import type { SplitRule, SplitRuleCreate } from '@/types/api';
import type { SplitRuleFormData } from '@/schemas/split';

interface SplitRulesSectionProps {
  splits: SplitRule[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  startOpen?: boolean;
}

const HIDDEN_RULES_KEY = 'opensplit-hidden-split-rules';

function readHiddenRuleIds() {
  if (typeof window === 'undefined') return [] as string[];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(HIDDEN_RULES_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : [];
  } catch {
    return [];
  }
}

function writeHiddenRuleIds(ruleIds: string[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(HIDDEN_RULES_KEY, JSON.stringify(ruleIds));
}

function apiErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.join('. ');
  if (typeof detail === 'string') return detail;
  return fallback;
}

export function SplitRulesSection({ splits, isLoading, isError, onRetry, startOpen = false }: SplitRulesSectionProps) {
  const [showForm, setShowForm] = useState(startOpen);
  const [editingRule, setEditingRule] = useState<SplitRule | null>(null);
  const [hiddenRuleIds, setHiddenRuleIds] = useState<string[]>(readHiddenRuleIds);
  const [showHiddenRules, setShowHiddenRules] = useState(false);
  const createSplit = useCreateSplit();
  const updateSplit = useUpdateSplit();
  const activateSplit = useActivateSplit();
  const deleteSplit = useDeleteSplit();

  const activeRule = useMemo(() => splits?.find((rule) => rule.active), [splits]);
  const inactiveRules = useMemo(() => splits?.filter((rule) => !rule.active) ?? [], [splits]);
  const activeTargets = useMemo(
    () => activeRule?.targets.filter((target) => target.percentage > 0) ?? [],
    [activeRule]
  );
  const activeTotal = activeTargets.reduce((sum, target) => sum + target.percentage, 0);
  const visibleInactiveRules = inactiveRules.filter((rule) => showHiddenRules || !hiddenRuleIds.includes(rule.id));
  const hiddenCount = inactiveRules.filter((rule) => hiddenRuleIds.includes(rule.id)).length;

  const handleCreate = useCallback(
    async (data: SplitRuleFormData) => {
      try {
        await createSplit.mutateAsync(data as SplitRuleCreate);
        toast.success('Split rule created');
        setShowForm(false);
      } catch {
        toast.error('Could not create split rule');
      }
    },
    [createSplit]
  );

  const handleUpdate = useCallback(
    async (data: SplitRuleFormData) => {
      if (!editingRule) return;
      try {
        await updateSplit.mutateAsync({ id: editingRule.id, data });
        toast.success('Split rule updated');
        setEditingRule(null);
      } catch {
        toast.error('Could not update split rule');
      }
    },
    [editingRule, updateSplit]
  );

  const handleActivate = useCallback(
    async (rule: SplitRule) => {
      try {
        await activateSplit.mutateAsync(rule.id);
        toast.success('Split rule activated');
      } catch (error) {
        const message = apiErrorMessage(error, 'Could not activate split rule');
        toast.error(message);
        setShowForm(false);
        setEditingRule(rule);
      }
    },
    [activateSplit]
  );

  const handleDelete = useCallback(
    async (rule: SplitRule) => {
      const confirmed = window.confirm(`Delete "${rule.name}"? This only removes a draft rule with no payment history.`);
      if (!confirmed) return;

      try {
        await deleteSplit.mutateAsync(rule.id);
        toast.success('Split rule deleted');
      } catch {
        toast.error('Only inactive rules without payment history can be deleted');
      }
    },
    [deleteSplit]
  );

  const handleHide = useCallback(
    (rule: SplitRule) => {
      const nextIds = Array.from(new Set([...hiddenRuleIds, rule.id]));
      setHiddenRuleIds(nextIds);
      writeHiddenRuleIds(nextIds);
      toast.success('Rule hidden from demo. Payment proof history stays intact.');
    },
    [hiddenRuleIds]
  );

  const handleRestore = useCallback(
    (rule: SplitRule) => {
      const nextIds = hiddenRuleIds.filter((id) => id !== rule.id);
      setHiddenRuleIds(nextIds);
      writeHiddenRuleIds(nextIds);
      toast.success('Rule restored to saved rules');
    },
    [hiddenRuleIds]
  );

  if (isLoading) {
    return (
      <Card className="bg-white/[0.055] shadow-none">
        <CardContent className="space-y-4 p-6">
          <Skeleton className="h-8 w-44" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load split rules" onRetry={onRetry} />;
  }

  if (showForm || editingRule) {
    const rule = editingRule;

    return (
      <Card className="bg-white/[0.055] shadow-none">
        <CardContent className="p-6">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#94A3B8]">
              {rule ? 'Edit split' : 'New split'}
            </p>
            <h2 className="mt-2 text-xl font-semibold text-[#F5F5F7]">
              {rule ? rule.name : 'Create split rule'}
            </h2>
          </div>
          <SplitRuleForm
            defaultValues={rule
              ? {
                  name: rule.name,
                  targets: rule.targets.map((target) => ({
                    label: target.label,
                    lnbits_wallet_id: target.lnbits_wallet_id || '',
                    ln_address: target.ln_address || '',
                    has_lnd_receiver: target.has_lnd_receiver ?? false,
                    percentage: target.percentage,
                    order: target.order,
                  })),
                }
              : undefined}
            onSubmit={rule ? handleUpdate : handleCreate}
            onCancel={() => {
              setShowForm(false);
              setEditingRule(null);
            }}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden bg-white/[0.055] shadow-none">
      <CardContent className="p-0">
        <section className="border-b border-white/[0.08] p-5 sm:p-6">
          <div className="grid gap-4 xl:grid-cols-[minmax(220px,0.42fr)_1fr_auto] xl:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#94A3B8]">Current rule</p>
                {activeRule && (
                  <span className="rounded-full border border-[#FF2E93]/24 bg-[#FF2E93]/[0.07] px-2.5 py-1 text-[11px] font-medium text-[#FF2E93]">
                    Active
                  </span>
                )}
              </div>
              <h2 className="mt-2 text-xl font-semibold text-[#F5F5F7]">{activeRule?.name ?? 'No active split'}</h2>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#94A3B8]">
                <span className="font-mono">{activeRule ? `v${activeRule.version}` : 'v-'}</span>
                <span>{activeTargets.length} targets</span>
                <span className="font-mono">{activeRule ? `${activeTotal.toFixed(0)}% allocated` : '0% allocated'}</span>
              </div>
            </div>

            <div className="w-full">
              {activeRule ? (
                <SplitBar targets={activeTargets.map((target) => ({ label: target.label, percentage: target.percentage }))} />
              ) : (
                <div className="rounded-lg border border-white/[0.08] bg-white/[0.035] px-4 py-3 text-sm text-[#94A3B8]">
                  Create one rule to route the next BTCPay payment.
                </div>
              )}
            </div>

            <div className="flex justify-start xl:justify-end">
              <Button size="sm" onClick={() => setShowForm(true)} className="w-full sm:w-auto sm:min-w-28">
                <Plus className="h-4 w-4" />
                New rule
              </Button>
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-3 border-b border-white/[0.08] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-[#94A3B8]" strokeWidth={1.8} />
            <div>
              <h2 className="font-semibold text-[#F5F5F7]">Saved rules</h2>
              <p className="mt-1 text-sm text-[#94A3B8]">
                {inactiveRules.length} inactive · only one rule can be active
              </p>
            </div>
          </div>
          {hiddenCount > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setShowHiddenRules((value) => !value)} className="w-full sm:w-auto">
              {showHiddenRules ? 'Hide archived' : `Show hidden (${hiddenCount})`}
            </Button>
          )}
        </div>

        <div className="divide-y divide-white/[0.08]">
          {visibleInactiveRules.length === 0 ? (
            <p className="p-5 text-sm text-[#94A3B8]">
              {hiddenCount > 0 ? 'All inactive rules are hidden from this demo.' : 'No inactive rules saved.'}
            </p>
          ) : visibleInactiveRules.map((rule) => {
            const isHidden = hiddenRuleIds.includes(rule.id);
            return (
              <div key={rule.id} className="grid gap-3 p-4 lg:grid-cols-[minmax(160px,0.34fr)_1fr_auto] lg:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-[#F5F5F7]">{rule.name}</p>
                    <span className="rounded-full border border-white/[0.10] bg-white/[0.05] px-2.5 py-1 text-[11px] font-medium text-[#94A3B8]">
                      {isHidden ? 'Hidden' : 'Inactive'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[#94A3B8]">Created {formatDate(rule.created_at)}</p>
                </div>

                <SplitBar
                  targets={rule.targets
                    .filter((target) => target.percentage > 0)
                    .map((target) => ({ label: target.label, percentage: target.percentage }))}
                />

                <div className="flex flex-wrap items-center gap-2 lg:min-w-[260px] lg:justify-end">
                  <Button variant="ghost" size="sm" onClick={() => setEditingRule(rule)} className="min-w-20">
                    Edit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleActivate(rule)} className="min-w-24">
                    Activate
                  </Button>
                  {rule.can_delete ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(rule)}
                      loading={deleteSplit.isPending}
                      className="min-w-20 text-[#FF2E93] hover:text-[#FF6AB6]"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </Button>
                  ) : isHidden ? (
                    <Button variant="ghost" size="sm" onClick={() => handleRestore(rule)} className="min-w-20">
                      Restore
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => handleHide(rule)} className="min-w-24">
                      <Archive className="h-4 w-4" />
                      Hide
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
