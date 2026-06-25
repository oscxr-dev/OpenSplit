import { useState, useCallback } from 'react';
import { Zap, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { AmountKeypad } from '@/components/pos/AmountKeypad';
import { InvoiceQR } from '@/components/pos/InvoiceQR';
import { PaymentStatus } from '@/components/pos/PaymentStatus';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardContent } from '@/components/ui/Card';
import { useCreateInvoice } from '@/hooks/useInvoices';
import { useBtcPrice, satsToUsd } from '@/hooks/useBtcPrice';

type PosState = 'input' | 'invoice' | 'payment';

export function PosPage() {
  const [state, setState] = useState<PosState>('input');
  const [amount, setAmount] = useState('');
  const [memo, setMemo] = useState('');
  const [invoiceId, setInvoiceId] = useState<string | null>(null);
  const [bolt11, setBolt11] = useState<string | null>(null);

  const createInvoice = useCreateInvoice();
  const { data: btcPrice } = useBtcPrice();

  const satsAmount = parseInt(amount, 10) || 0;
  const usdAmount = btcPrice ? satsToUsd(satsAmount, btcPrice) : null;

  const handleGenerateInvoice = useCallback(async () => {
    if (satsAmount <= 0) {
      toast.error('Enter an amount in sats');
      return;
    }

    try {
      const invoice = await createInvoice.mutateAsync({
        amount_sats: satsAmount,
        memo: memo || undefined,
      });

      setInvoiceId(invoice.id);
      setBolt11(invoice.bolt11);
      setState('payment');
    } catch {
      toast.error('Could not generate payment. Try again.');
    }
  }, [satsAmount, memo, createInvoice]);

  const handleNewInvoice = useCallback(() => {
    setState('input');
    setAmount('');
    setMemo('');
    setInvoiceId(null);
    setBolt11(null);
  }, []);

  // Input state
  if (state === 'input') {
    return (
      <div className="mx-auto max-w-3xl space-y-4 sm:space-y-5">
        <div className="text-center">
          <p className="text-xs font-medium tracking-[0.12em] text-white/35 uppercase">Point of sale</p>
          <h1 className="mt-1 text-2xl font-semibold text-white/90 sm:text-3xl">New payment</h1>
          <p className="mt-1 text-sm text-white/40">Enter the amount in sats</p>
        </div>

        <Card>
          <CardContent className="pt-5 sm:pt-6">
            <div className="mb-4 text-center sm:mb-5">
              <div className="mb-1 text-4xl font-bold tabular-nums text-white/90 sm:text-5xl">
                {amount || '0'}
              </div>
              <div className="text-sm text-gray-400">
                sats
                {usdAmount !== null && usdAmount > 0 && (
                  <span className="ml-2 text-gray-500">
                    &asymp; ${usdAmount < 0.01 ? '<$0.01' : usdAmount.toFixed(2)} USD
                  </span>
                )}
              </div>
            </div>

            <AmountKeypad value={amount} onChange={setAmount} />
          </CardContent>
        </Card>

        <div className="space-y-3 pb-16 sm:pb-20">
          <Input
            label="Description (optional)"
            placeholder="Example: Americano coffee"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />

          <Button
            onClick={handleGenerateInvoice}
            loading={createInvoice.isPending}
            disabled={satsAmount <= 0}
            size="lg"
            className="w-full"
          >
            <Zap className="w-5 h-5" />
            Generate payment
          </Button>
        </div>
      </div>
    );
  }

  // Payment state
  if (state === 'payment' && invoiceId) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-white/90">Payment generated</h1>
          <p className="text-sm text-gray-500 mt-1">Waiting for Lightning payment...</p>
        </div>

        <Card>
          <CardContent className="pt-6">
            {bolt11 && (
              <InvoiceQR bolt11={bolt11} amount={satsAmount} />
            )}

            {memo && (
              <div className="flex items-center gap-2 text-sm text-gray-500 mt-4 justify-center">
                <FileText className="w-4 h-4" />
                {memo}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <PaymentStatus
              paymentId={invoiceId}
              onNewInvoice={handleNewInvoice}
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return null;
}
