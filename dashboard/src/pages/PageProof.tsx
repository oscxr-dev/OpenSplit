import { FileQuestion } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useInvoice } from '@/hooks/useInvoices';
import { SplitProofReceipt } from '@/components/payments/SplitProofReceipt';
import { EmptyState } from '@/components/shared/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';

/**
 * Authenticated permalink to a single payment's Split Proof (/proof/:paymentId).
 * Loads the payment via the existing tenant-scoped GET /payments/{id} and hands
 * it to the shared SplitProofReceipt (which fetches the proof itself). The
 * proof/payment endpoints are tenant-scoped, so another workspace's — or a
 * nonexistent — id returns 404, which we render as a clean not-found state.
 */
export function PageProof() {
  const { t } = useTranslation();
  const { paymentId } = useParams<{ paymentId: string }>();
  const { data: payment, isLoading, isError } = useInvoice(paymentId ?? '');

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-[520px] w-full" />
      </div>
    );
  }

  if (isError || !payment) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState
          icon={<FileQuestion className="h-8 w-8 text-[#94A3B8]" />}
          message={t('proof.notFound')}
          description={t('proof.notFoundDescription')}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <SplitProofReceipt payment={payment} />
    </div>
  );
}
