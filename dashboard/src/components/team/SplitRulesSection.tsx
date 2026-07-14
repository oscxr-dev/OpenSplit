import { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import { Pencil, Plus, PowerOff, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useActivateSplit, useCreateSplit, useDeactivateSplit, useDeleteSplit, useUpdateSplit } from '@/hooks/useSplits';
import { SplitBar } from '@/components/splits/SplitBar';
import { SplitRuleForm } from '@/components/splits/SplitRuleForm';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/shared/ErrorState';
import { filterRules, type RuleLibraryFilter } from '@/lib/ruleLibrary';
import { cn } from '@/lib/utils';
import type { SplitRule, SplitRuleCreate } from '@/types/api';
import type { SplitRuleFormData } from '@/schemas/split';

interface SplitRulesSectionProps {
  splits: SplitRule[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  startOpen?: boolean;
}

const LIBRARY_FILTERS: Array<{ value: RuleLibraryFilter; labelKey: string }> = [
  { value: 'all', labelKey: 'splits.filter.all' },
  { value: 'active', labelKey: 'splits.filter.active' },
  { value: 'inactive', labelKey: 'splits.filter.inactive' },
];

function apiErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.join('. ');
  if (typeof detail === 'string') return detail;
  return fallback;
}

function previewTargets(rule: SplitRule) {
  return rule.targets
    .filter((target) => target.percentage > 0)
    .map((target) => ({ label: target.label, percentage: target.percentage }));
}

export function SplitRulesSection({ splits, isLoading, isError, onRetry, startOpen = false }: SplitRulesSectionProps) {
  const { t } = useTranslation();
  const [showForm, setShowForm] = useState(startOpen);
  const [editingRule, setEditingRule] = useState<SplitRule | null>(null);
  // Bumped on every close so the next time the modal opens the form gets a brand
  // new key → a guaranteed fresh React Hook Form instance (no leaked state).
  const [formGeneration, setFormGeneration] = useState(0);
  const [confirmDeleteRule, setConfirmDeleteRule] = useState<SplitRule | null>(null);
  const [search, setSearch] = useState('');
  const [libraryFilter, setLibraryFilter] = useState<RuleLibraryFilter>('all');
  const createSplit = useCreateSplit();
  const updateSplit = useUpdateSplit();
  const activateSplit = useActivateSplit();
  const deactivateSplit = useDeactivateSplit();
  const deleteSplit = useDeleteSplit();

  const allRules = useMemo(() => splits ?? [], [splits]);

  // Active-rule count for the library subtitle. The active-rule tabs + Current
  // Rule visualization now live on the TeamMap graph (see MembersPage).
  const activeRules = useMemo(() => allRules.filter((rule) => rule.active), [allRules]);

  const libraryRules = useMemo(
    () => filterRules(allRules, search, libraryFilter),
    [allRules, search, libraryFilter]
  );

  const closeForm = useCallback(() => {
    setShowForm(false);
    setEditingRule(null);
    setFormGeneration((generation) => generation + 1);
  }, []);

  const handleCreate = useCallback(
    async (data: SplitRuleFormData) => {
      try {
        await createSplit.mutateAsync(data as SplitRuleCreate);
        toast.success(t('splits.created'));
        closeForm();
      } catch {
        toast.error(t('splits.createError'));
      }
    },
    [createSplit, closeForm, t]
  );

  const handleUpdate = useCallback(
    async (data: SplitRuleFormData) => {
      if (!editingRule) return;
      try {
        await updateSplit.mutateAsync({ id: editingRule.id, data });
        toast.success(t('splits.updated'));
        closeForm();
      } catch {
        toast.error(t('splits.updateError'));
      }
    },
    [editingRule, updateSplit, closeForm, t]
  );

  const handleActivate = useCallback(
    async (rule: SplitRule) => {
      try {
        await activateSplit.mutateAsync(rule.id);
        toast.success(t('splits.activated'));
      } catch (error) {
        toast.error(apiErrorMessage(error, t('splits.activateError')));
      }
    },
    [activateSplit, t]
  );

  const handleDeactivate = useCallback(
    async (rule: SplitRule) => {
      try {
        await deactivateSplit.mutateAsync(rule.id);
        toast.success(t('splits.deactivated'));
      } catch (error) {
        toast.error(apiErrorMessage(error, t('splits.deactivateError')));
      }
    },
    [deactivateSplit, t]
  );

  // Clicking Delete in the edit modal opens a custom confirmation modal instead
  // of window.confirm. Active rules are blocked outright (no confirm needed).
  const handleDelete = useCallback(
    (rule: SplitRule) => {
      if (rule.active) {
        toast.error(t('splits.deactivateFirst'));
        return;
      }
      setConfirmDeleteRule(rule);
    },
    [t]
  );

  const confirmDelete = useCallback(async () => {
    if (!confirmDeleteRule) return;
    try {
      await deleteSplit.mutateAsync(confirmDeleteRule.id);
      toast.success(t('splits.deleted'));
      setConfirmDeleteRule(null);
      closeForm();
    } catch {
      toast.error(t('splits.deleteError'));
    }
  }, [confirmDeleteRule, deleteSplit, closeForm, t]);

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
    return <ErrorState message={t('splits.loadError')} onRetry={onRetry} />;
  }

  const formOpen = showForm || editingRule !== null;

  return (
    <Card className="overflow-hidden bg-white/[0.055] shadow-none">
      <CardContent className="p-0">
        {/* Rule Library (the active-rule tabs + Current Rule board now live on
            top of the TeamMap graph in MembersPage). */}
        <section className="p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="font-semibold text-[#F5F5F7]">{t('splits.ruleLibrary')}</h2>
              <p className="mt-1 text-sm text-[#94A3B8]">
                {t('splits.libraryCounts', { active: activeRules.length, inactive: allRules.length - activeRules.length })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t('splits.searchPlaceholder')}
                  className="pl-9"
                  aria-label={t('splits.searchPlaceholder')}
                />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setEditingRule(null);
                  setShowForm(true);
                }}
                className="shrink-0"
              >
                <Plus className="h-4 w-4" />
                {t('splits.newRule')}
              </Button>
            </div>
          </div>

          <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
            {LIBRARY_FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setLibraryFilter(option.value)}
                className={cn(
                  'shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  libraryFilter === option.value
                    ? 'border border-[#FF2E93]/28 bg-[#FF2E93]/[0.10] text-[#F5F5F7]'
                    : 'border border-white/[0.08] bg-white/[0.03] text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                )}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>

          <div className="mt-4 overflow-hidden rounded-lg border border-white/[0.08]">
            {libraryRules.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-[#94A3B8]">
                {allRules.length === 0 ? t('splits.noRulesYet') : t('splits.noRulesMatch')}
              </p>
            ) : (
              <div className="divide-y divide-white/[0.08]">
                {libraryRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-4"
                  >
                    {/* Name + status */}
                    <button
                      type="button"
                      onClick={() => {
                        setShowForm(false);
                        setEditingRule(rule);
                      }}
                      className="group flex min-w-0 items-center gap-2 text-left sm:w-52 sm:shrink-0"
                      title={t('splits.editRule')}
                    >
                      <span className="truncate font-medium text-[#F5F5F7] group-hover:text-white">{rule.name}</span>
                      <span
                        className={cn(
                          'shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                          rule.active
                            ? 'border-[#FF2E93]/24 bg-[#FF2E93]/[0.08] text-[#FF2E93]'
                            : 'border-white/[0.10] bg-white/[0.04] text-[#94A3B8]'
                        )}
                      >
                        {rule.active ? t('splits.active') : t('splits.inactive')}
                      </span>
                    </button>

                    {/* Compact split preview */}
                    <div className="min-w-0 flex-1">
                      <SplitBar variant="library" showLegend={false} targets={previewTargets(rule)} />
                    </div>

                    {/* Primary action */}
                    <div className="flex shrink-0 items-center gap-1.5 sm:justify-end">
                      {rule.active ? (
                        <Button variant="ghost" size="sm" onClick={() => handleDeactivate(rule)} className="min-w-24">
                          <PowerOff className="h-4 w-4" />
                          {t('splits.deactivate')}
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" onClick={() => handleActivate(rule)} className="min-w-24">
                          {t('splits.activate')}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setShowForm(false);
                          setEditingRule(rule);
                        }}
                        className="px-2"
                        aria-label={t('splits.editAria', { name: rule.name })}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </CardContent>

      {/* Create / edit drawer */}
      <Dialog
        open={formOpen}
        onClose={closeForm}
        title={editingRule ? t('splits.editTitle', { name: editingRule.name }) : t('splits.createTitle')}
        className="max-w-2xl"
        adaptive
      >
        {/* Render the form only while open, keyed per target, so RHF state never
            leaks between opens: "New rule" always mounts a fresh, empty form and
            editing a rule mounts with that rule's data. */}
        {formOpen && (
          <>
            <SplitRuleForm
              key={`${editingRule?.id ?? 'new'}-${formGeneration}`}
              defaultValues={editingRule
                ? {
                    name: editingRule.name,
                    targets: editingRule.targets.map((target) => ({
                      label: target.label,
                      lnbits_wallet_id: target.lnbits_wallet_id || '',
                      ln_address: target.ln_address || '',
                      has_lnd_receiver: target.has_lnd_receiver ?? false,
                      percentage: target.percentage,
                      order: target.order,
                    })),
                  }
                : undefined}
              onSubmit={editingRule ? handleUpdate : handleCreate}
              onCancel={closeForm}
            />
            {editingRule && (
              <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/[0.08] pt-4">
                <p className="text-xs text-[#94A3B8]">
                  {editingRule.active ? t('splits.deactivateBeforeDeleting') : t('splits.onlyDraftDeletable')}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(editingRule)}
                  loading={deleteSplit.isPending}
                  className="text-[#FF2E93] hover:text-[#FF6AB6]"
                >
                  <Trash2 className="h-4 w-4" />
                  {t('common.delete')}
                </Button>
              </div>
            )}
          </>
        )}
      </Dialog>

      {/* Delete confirmation — replaces window.confirm; stacks above the edit modal. */}
      <ConfirmDialog
        open={confirmDeleteRule !== null}
        title={t('splits.deleteConfirmTitle')}
        description={t('splits.deleteConfirmDescription')}
        confirmLabel={t('common.delete')}
        cancelLabel={t('common.cancel')}
        destructive
        loading={deleteSplit.isPending}
        onConfirm={confirmDelete}
        onClose={() => setConfirmDeleteRule(null)}
      />
    </Card>
  );
}
