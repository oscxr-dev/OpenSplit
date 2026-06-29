import { formatDistanceToNow } from 'date-fns';

/** Human "x ago" for a public last-activity timestamp (privacy-safe metadata). */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return 'No activity yet';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'No activity yet';
  return formatDistanceToNow(date, { addSuffix: true });
}
