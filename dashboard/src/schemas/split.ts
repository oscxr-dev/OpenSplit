import { z } from 'zod';

const hasUsefulLightningAddress = (value?: string) => {
  if (!value) return false;
  const text = value.trim();
  if (!text || text.includes(' ') || !text.includes('@')) return false;
  const [local, domain] = text.split('@');
  return Boolean(local && domain && domain.includes('.'));
};

const hasUsefulWalletId = (value?: string) => {
  if (!value) return false;
  const text = value.trim();
  return text.length >= 16 && /[a-z]/i.test(text);
};

export const targetSchema = z.object({
  label: z.string().trim().min(1, 'Label is required'),
  ln_address: z.string().trim().optional(),
  lnbits_wallet_id: z.string().trim().optional(),
  // True when the backend reports a dynamic LND receiver for this label; such
  // a target mints its own invoice and needs no Lightning address.
  has_lnd_receiver: z.boolean().optional(),
  percentage: z
    .number()
    .min(0.01, 'Percentage must be greater than 0')
    .max(100, 'Percentage cannot exceed 100'),
  order: z.number().int().min(0),
}).superRefine((target, ctx) => {
  if (
    !target.has_lnd_receiver &&
    !hasUsefulLightningAddress(target.ln_address) &&
    !hasUsefulWalletId(target.lnbits_wallet_id)
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['ln_address'],
      message: 'Add a valid Lightning address, for example name@wallet.com',
    });
  }
});

export const splitRuleSchema = z.object({
  name: z.string().trim().min(1, 'Rule name is required').max(100),
  targets: z
    .array(targetSchema)
    .min(1, 'At least one destination is required')
    .refine(
      (targets) => {
        // Partial split rules are allowed: the total may be anywhere in (0, 100].
        // Any unallocated remainder stays in the store. Over-allocation is blocked.
        const sum = targets.reduce((acc, t) => acc + t.percentage, 0);
        return sum > 0 && sum <= 100.001;
      },
      { message: 'Percentages cannot exceed 100%' }
    ),
});

export type SplitRuleFormData = z.infer<typeof splitRuleSchema>;
export type TargetFormData = z.infer<typeof targetSchema>;
