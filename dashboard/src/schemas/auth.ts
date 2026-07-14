import { z } from 'zod';

// Validation messages are i18n KEYS — the form translates them at render time
// (see LoginPage), so the schema itself stays static and language-agnostic.
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'errors.validation.emailRequired')
    .email('errors.validation.emailInvalid'),
  password: z
    .string()
    .min(1, 'errors.validation.passwordRequired')
    .min(4, 'errors.validation.passwordMin'),
});

export type LoginFormData = z.infer<typeof loginSchema>;
