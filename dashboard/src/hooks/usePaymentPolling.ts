import { useState, useEffect, useCallback, useRef } from 'react';
import api from '@/lib/api';
import type { Invoice } from '@/types/api';

const POLL_INTERVAL = 2000;
const TIMEOUT = 5 * 60 * 1000; // 5 minutes

interface UsePaymentPollingResult {
  invoice: Invoice | null;
  isPaid: boolean;
  isPending: boolean;
  isTimeout: boolean;
  error: string | null;
}

export function usePaymentPolling(invoiceId: string | null): UsePaymentPollingResult {
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [isPaid, setIsPaid] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [isTimeout, setIsTimeout] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startTime = useRef<number>(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async (id: string) => {
    try {
      const res = await api.get(`/invoices/${id}`);
      const inv: Invoice = res.data;
      setInvoice(inv);

      if (inv.status === 'paid') {
        setIsPaid(true);
        setIsPending(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } else if (Date.now() - startTime.current > TIMEOUT) {
        setIsTimeout(true);
        setIsPending(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al consultar pago');
      setIsPending(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    if (!invoiceId) {
      setInvoice(null);
      setIsPaid(false);
      setIsPending(false);
      setIsTimeout(false);
      setError(null);
      return;
    }

    startTime.current = Date.now();
    setIsPending(true);
    setIsPaid(false);
    setIsTimeout(false);
    setError(null);

    // Poll immediately
    poll(invoiceId);

    intervalRef.current = setInterval(() => poll(invoiceId), POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [invoiceId, poll]);

  return { invoice, isPaid, isPending, isTimeout, error };
}
