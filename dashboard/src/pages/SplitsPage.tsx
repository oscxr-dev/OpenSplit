import { useState, useCallback } from 'react';
import { Plus, GitBranch } from 'lucide-react';
import { toast } from 'sonner';
import { useSplits, useCreateSplit, useUpdateSplit, useActivateSplit } from '@/hooks/useSplits';
import { SplitBar } from '@/components/splits/SplitBar';
import { SplitRuleForm } from '@/components/splits/SplitRuleForm';
import { Card, CardContent, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { formatDate } from '@/lib/utils';
import type { SplitRule, SplitRuleCreate } from '@/types/api';
import type { SplitRuleFormData } from '@/schemas/split';

export function SplitsPage() {
  const { data: splits, isLoading, isError, refetch } = useSplits();
  const createSplit = useCreateSplit();
  const updateSplit = useUpdateSplit();
  const activateSplit = useActivateSplit();

  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<SplitRule | null>(null);

  const activeRule = splits?.find((r) => r.active);

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
      } catch {
        toast.error('Could not activate split rule');
      }
    },
    [activateSplit]
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load split rules" onRetry={() => refetch()} />;
  }

  if (showForm) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-white/90">New rule</h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <SplitRuleForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (editingRule) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-white/90">Edit rule</h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <SplitRuleForm
              defaultValues={{
                name: editingRule.name,
                targets: editingRule.targets.map((t) => ({
                  label: t.label,
                  lnbits_wallet_id: t.lnbits_wallet_id || '',
                  ln_address: t.ln_address || '',
                  percentage: t.percentage,
                  order: t.order,
                })),
              }}
              onSubmit={handleUpdate}
              onCancel={() => setEditingRule(null)}
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!splits || splits.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-white/90">Splits</h1>
        </div>
        <EmptyState
          icon={<GitBranch className="w-8 h-8 text-gray-400" />}
          message="No split rules"
          description="Create rules to divide payments between different wallets"
          actionLabel="New rule"
          onAction={() => setShowForm(true)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium tracking-[0.12em] text-white/35 uppercase">Automation</p>
          <h1 className="mt-1 text-2xl font-semibold text-white/90 sm:text-3xl">Splits</h1>
        </div>
        <Button onClick={() => setShowForm(true)} size="sm">
          <Plus className="w-4 h-4" />
          New rule
        </Button>
      </div>

      {/* Active rule */}
      {activeRule && (
        <Card className="border-orange-300/15 bg-gradient-to-br from-orange-400/[0.08] to-transparent">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">{activeRule.name}</h3>
                <Badge>Active</Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEditingRule(activeRule)}
              >
                Edit
              </Button>
            </div>
            <p className="text-xs text-gray-400">Created {formatDate(activeRule.created_at)}</p>
          </CardHeader>
          <CardContent>
            <SplitBar
              targets={activeRule.targets.map((t) => ({
                label: t.label,
                percentage: t.percentage,
              })).filter((target) => target.percentage > 0)}
            />
          </CardContent>
        </Card>
      )}

      {/* Inactive rules */}
      <div className="space-y-3">
        {splits
          .filter((r) => !r.active)
          .map((rule) => (
            <Card key={rule.id} className="opacity-65 transition-all hover:border-white/15 hover:bg-white/[0.075] hover:opacity-100">
              <CardContent className="pt-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-700">{rule.name}</h3>
                    <Badge variant="default">Inactive</Badge>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingRule(rule)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleActivate(rule)}
                    >
                      Activate
                    </Button>
                  </div>
                </div>
                <SplitBar
                  targets={rule.targets.map((t) => ({
                    label: t.label,
                    percentage: t.percentage,
                  })).filter((target) => target.percentage > 0)}
                />
                <p className="text-xs text-gray-400 mt-2">
                  Created {formatDate(rule.created_at)}
                </p>
              </CardContent>
            </Card>
          ))}
      </div>
    </div>
  );
}
