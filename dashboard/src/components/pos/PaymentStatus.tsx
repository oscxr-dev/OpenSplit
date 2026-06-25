import { CheckCircle, Clock, AlertCircle, RefreshCw } from 'lucide-react';
import { usePaymentPolling } from '@/hooks/usePaymentPolling';
import { SplitBar } from '@/components/splits/SplitBar';
import { formatSats, formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';

interface PaymentStatusProps {
  paymentId: string;
  onNewInvoice: () => void;
}

export function PaymentStatus({ paymentId, onNewInvoice }: PaymentStatusProps) {
  const { invoice, isPaid, isPending, isTimeout, error } = usePaymentPolling(paymentId);

  if (!invoice && isPending) {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <div className="flex gap-1">
          <span className="w-3 h-3 rounded-full bg-bitcoin animate-pulse-dot" />
          <span className="w-3 h-3 rounded-full bg-bitcoin animate-pulse-dot" />
          <span className="w-3 h-3 rounded-full bg-bitcoin animate-pulse-dot" />
        </div>
        <p className="text-gray-600 font-medium">Waiting for payment...</p>
        <p className="text-sm text-gray-400">Scan the QR code with your Lightning wallet</p>
      </div>
    );
  }

  if (isTimeout) {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <div className="w-16 h-16 rounded-full bg-yellow-100 flex items-center justify-center">
          <Clock className="w-8 h-8 text-yellow-600" />
        </div>
        <p className="text-gray-900 font-semibold">Payment timed out</p>
        <p className="text-sm text-gray-500">The invoice was not paid within 5 minutes</p>
        <Button onClick={onNewInvoice} variant="outline">
          New payment
        </Button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-600" />
        </div>
        <p className="text-gray-900 font-semibold">Could not verify payment</p>
        <p className="text-sm text-gray-500">{error}</p>
        <Button onClick={onNewInvoice} variant="outline">
          New payment
        </Button>
      </div>
    );
  }

  if (isPaid && invoice) {
    return (
      <div className="flex flex-col gap-6 py-8">
        <div className="flex flex-col items-center gap-3">
          <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center animate-bounce">
            <CheckCircle className="w-10 h-10 text-green-600" />
          </div>
          <p className="text-xl font-bold text-green-700">Payment received</p>
          <Badge variant="success">Paid</Badge>
          <p className="text-sm text-gray-500">{formatDate(invoice.paid_at)}</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
          <h4 className="text-sm font-semibold text-gray-500 mb-3 uppercase tracking-wider">
            Split
          </h4>
          {invoice.splits && invoice.splits.length > 0 ? (
            <>
              <SplitBar
                targets={invoice.splits.map((s) => ({
                  label: s.label || 'Unlabeled',
                  percentage:
                    invoice.amount_sats > 0
                      ? Math.round((s.amount_sats / invoice.amount_sats) * 100)
                      : 0,
                  amount_sats: s.amount_sats,
                }))}
              />
              <div className="mt-4 space-y-2">
                {invoice.splits.map((split) => (
                  <div
                    key={split.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-gray-700">{split.label || 'Unlabeled'}</span>
                    <span className="font-medium text-gray-900">
                      {formatSats(split.amount_sats)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">No split configured</p>
          )}
          <div className="mt-4 pt-3 border-t border-gray-100 flex justify-between">
            <span className="font-semibold text-gray-700">Total</span>
            <span className="font-bold text-bitcoin">
              {formatSats(invoice.amount_sats)}
            </span>
          </div>
        </div>

        <Button onClick={onNewInvoice} size="lg" className="w-full">
          <RefreshCw className="w-4 h-4" />
          New payment
        </Button>
      </div>
    );
  }

  return null;
}
