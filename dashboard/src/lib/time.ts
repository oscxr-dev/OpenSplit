import { formatDistanceToNow } from 'date-fns';
import i18n, { dateFnsLocale } from '@/i18n';

/** Human "x ago" for a public last-activity timestamp (privacy-safe metadata). */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return i18n.t('time.noActivity');
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return i18n.t('time.noActivity');
  return formatDistanceToNow(date, { addSuffix: true, locale: dateFnsLocale() });
}
