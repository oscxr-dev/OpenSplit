import { useState, useCallback } from 'react';
import { Plus, Trash2, GripVertical, Zap } from 'lucide-react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { splitRuleSchema, type SplitRuleFormData } from '@/schemas/split';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

const TARGET_COLORS = [
  'bg-bitcoin',
  'bg-emerald-500',
  'bg-violet-500',
  'bg-rose-500',
  'bg-amber-500',
  'bg-cyan-500',
  'bg-pink-500',
  'bg-indigo-500',
];

interface SplitRuleFormProps {
  defaultValues?: Partial<SplitRuleFormData>;
  onSubmit: (data: SplitRuleFormData) => Promise<void>;
  onCancel: () => void;
}

export function SplitRuleForm({ defaultValues, onSubmit, onCancel }: SplitRuleFormProps) {
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<SplitRuleFormData>({
    resolver: zodResolver(splitRuleSchema),
    defaultValues: defaultValues || {
      name: '',
      targets: [{ label: '', ln_address: '', lnbits_wallet_id: '', percentage: 0, order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'targets',
  });

  const targets = watch('targets');
  const totalPercentage = targets?.reduce((sum, t) => sum + (Number(t.percentage) || 0), 0) || 0;
  const diffFrom100 = Math.round((100 - totalPercentage) * 100) / 100;
  const isValidTotal = Math.abs(diffFrom100) < 0.01 && totalPercentage > 0;

  const handleFormSubmit = useCallback(
    async (data: SplitRuleFormData) => {
      setSubmitting(true);
      try {
        const ordered = data.targets.map((t, i) => ({
          ...t,
          label: t.label.trim(),
          ln_address: t.ln_address?.trim() || undefined,
          lnbits_wallet_id: t.lnbits_wallet_id?.trim() || undefined,
          order: i,
          percentage: Number(t.percentage),
        }));
        await onSubmit({ ...data, targets: ordered });
      } finally {
        setSubmitting(false);
      }
    },
    [onSubmit]
  );

  function addTarget() {
    append({ label: '', ln_address: '', lnbits_wallet_id: '', percentage: 0, order: fields.length });
  }

  function splitEvenly() {
    if (!fields.length) return;
    const base = Math.floor((100 / fields.length) * 10) / 10;
    const values = fields.map((_, index) => {
      if (index === fields.length - 1) {
        return Math.round((100 - base * (fields.length - 1)) * 10) / 10;
      }
      return base;
    });
    values.forEach((value, index) => {
      setValue(`targets.${index}.percentage`, value, { shouldDirty: true, shouldValidate: true });
    });
  }

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
      <Input
        label="Rule name"
        placeholder="Example: BitCrew"
        error={errors.name?.message}
        {...register('name')}
      />

      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-gray-700">Destinations</h4>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={splitEvenly}>
              Split evenly
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={addTarget}>
              <Plus className="w-4 h-4" />
              Add
            </Button>
          </div>
        </div>

        {fields.map((field, index) => (
          <div
            key={field.id}
            className="space-y-2.5 rounded-lg border border-white/[0.08] bg-white/[0.035] p-3"
          >
            <div className="flex items-center gap-2">
              <GripVertical className="w-4 h-4 text-gray-300 flex-shrink-0" />
              <span
                className={cn(
                  'w-2.5 h-2.5 rounded-full flex-shrink-0',
                  TARGET_COLORS[index % TARGET_COLORS.length]
                )}
              />
              <span className="text-xs font-medium text-gray-400">
                Destination {index + 1}
              </span>
              {fields.length > 1 && (
                <button
                  type="button"
                  onClick={() => remove(index)}
                  className="ml-auto p-1 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_140px]">
              <Input
                label="Label"
                placeholder="Example: Partner 1"
                error={errors.targets?.[index]?.label?.message}
                {...register(`targets.${index}.label`)}
              />
              {targets?.[index]?.has_lnd_receiver ? (
                <div className="w-full">
                  <span className="mb-1.5 block text-xs font-medium text-white/55">
                    Lightning address
                  </span>
                  <div className="flex items-center gap-2 rounded-xl border border-emerald-300/15 bg-emerald-400/10 px-4 py-2.5 text-sm text-emerald-300">
                    <Zap className="h-4 w-4 flex-shrink-0" strokeWidth={1.8} />
                    LND receiver configured
                  </div>
                </div>
              ) : (
                <Input
                  label="Lightning address"
                  placeholder="name@wallet.com"
                  error={errors.targets?.[index]?.ln_address?.message}
                  {...register(`targets.${index}.ln_address`)}
                />
              )}
              <Input
                label="Percentage (%)"
                type="number"
                step="0.1"
                min="0"
                max="100"
                placeholder="50"
                error={errors.targets?.[index]?.percentage?.message}
                {...register(`targets.${index}.percentage`, { valueAsNumber: true })}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Total indicator */}
      <div
        className={cn(
          'flex items-center justify-between px-4 py-3 rounded-xl text-sm font-medium',
          isValidTotal
            ? 'border border-emerald-300/10 bg-emerald-400/10 text-emerald-300'
            : totalPercentage > 0
              ? 'border border-red-300/10 bg-red-400/10 text-red-300'
              : 'border border-white/[0.07] bg-white/[0.035] text-white/40'
        )}
      >
        <span>Total</span>
        <span className="tabular-nums font-bold">
          {totalPercentage.toFixed(1)}%
          {!isValidTotal && totalPercentage > 0 && (
            <span className="ml-1 text-xs">
              ({diffFrom100 > 0 ? `+${diffFrom100}%` : `${diffFrom100}%`})
            </span>
          )}
        </span>
      </div>

      {errors.targets?.root?.message && (
        <p className="text-sm text-red-600">{errors.targets.root.message}</p>
      )}
      {typeof errors.targets?.message === 'string' && (
        <p className="text-sm text-red-600">{errors.targets.message}</p>
      )}

      <div className="flex gap-3 pt-2">
        <Button type="button" variant="ghost" onClick={onCancel} className="flex-1">
          Cancel
        </Button>
        <Button
          type="submit"
          loading={submitting}
          disabled={!isValidTotal}
          className="flex-1"
        >
          Save
        </Button>
      </div>
    </form>
  );
}
