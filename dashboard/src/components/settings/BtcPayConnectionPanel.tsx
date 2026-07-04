import { useEffect, useState } from 'react';
import axios from 'axios';
import { Check, ExternalLink, Minus, PlugZap, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/hooks/useAuth';
import api from '@/lib/api';
import { isDockerHostUrl, isValidServerUrl, toBrowserUrl } from '@/lib/browserUrl';
import { cn } from '@/lib/utils';
import type { BtcPayAuthorizeUrl, BtcPayConnectionTest } from '@/types/api';

function apiErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === 'string' ? item : item?.msg))
      .filter(Boolean);
    if (messages.length) return messages.join('. ');
  }
  return fallback;
}

/** One row of the connection-test checklist. `state === null` means the check
 *  never ran because an earlier step already failed. */
function CheckRow({ label, state }: { label: string; state: boolean | null }) {
  const status = state === null ? 'not checked' : state ? 'passed' : 'failed';
  const Icon = state === null ? Minus : state ? Check : X;
  return (
    <li aria-label={`${label}: ${status}`} className="flex items-center gap-2.5 text-sm">
      <span
        className={cn(
          'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border',
          state === null && 'border-white/[0.14] bg-white/[0.05] text-[#94A3B8]',
          state === true && 'border-emerald-300/25 bg-emerald-400/10 text-emerald-300',
          state === false && 'border-red-300/25 bg-red-400/10 text-red-300'
        )}
      >
        <Icon className="h-3 w-3" strokeWidth={2.5} />
      </span>
      <span className={cn('font-medium', state === false ? 'text-red-300' : 'text-[#F5F5F7]')}>
        {label}
      </span>
      {state === null && <span className="text-xs text-[#94A3B8]">not checked</span>}
    </li>
  );
}

export function BtcPayConnectionPanel() {
  const { tenant, refreshTenant } = useAuth();
  const info = tenant?.tenant;
  const savedUrl = info?.btcpay_url ?? '';
  const savedStoreId = info?.btcpay_store_id ?? '';
  const keySet = Boolean(info?.btcpay_api_key_set);
  const keyLast4 = info?.btcpay_api_key_last4 ?? null;

  const [url, setUrl] = useState(savedUrl);
  const [storeId, setStoreId] = useState(savedStoreId);
  // The API key input is write-only: a stored key is NEVER echoed back here.
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [opening, setOpening] = useState(false);
  const [testResult, setTestResult] = useState<BtcPayConnectionTest | null>(null);

  // Hydrate from the tenant on load and after each successful save/refetch.
  useEffect(() => setUrl(savedUrl), [savedUrl]);
  useEffect(() => setStoreId(savedStoreId), [savedStoreId]);

  const configured = Boolean(savedUrl && savedStoreId && keySet);
  const connected = configured && tenant?.connection_status === 'ok';

  // Dirty per field: any input differing from the stored configuration.
  const trimmedUrl = url.trim();
  const trimmedStoreId = storeId.trim();
  const trimmedKey = apiKey.trim();
  const dirty =
    trimmedUrl !== savedUrl || trimmedStoreId !== savedStoreId || trimmedKey.length > 0;

  const urlError =
    trimmedUrl && trimmedUrl !== savedUrl && !isValidServerUrl(trimmedUrl)
      ? 'Enter a full URL — https://btcpay.example.com, http://localhost:3003, or http://host.docker.internal:3003'
      : undefined;

  // Only meaningful diffs are sent; blanks never wipe stored values (the
  // backend enforces the same PATCH semantics).
  const pendingPayload: Record<string, string> = {};
  if (trimmedUrl && trimmedUrl !== savedUrl) pendingPayload.btcpay_url = trimmedUrl;
  if (trimmedStoreId && trimmedStoreId !== savedStoreId) pendingPayload.btcpay_store_id = trimmedStoreId;
  if (trimmedKey) pendingPayload.btcpay_api_key = trimmedKey;
  const canSave = Object.keys(pendingPayload).length > 0 && !urlError;

  function discardChanges() {
    setUrl(savedUrl);
    setStoreId(savedStoreId);
    setApiKey('');
  }

  async function saveConnection() {
    if (!canSave) return;
    setSaving(true);
    try {
      await api.patch('/tenants/me', pendingPayload);
      await refreshTenant();
      setApiKey('');
      setTestResult(null); // stale against the new configuration
      toast.success('BTCPay connection saved');
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Could not save BTCPay connection'));
    } finally {
      setSaving(false);
    }
  }

  async function runTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post<BtcPayConnectionTest>('/tenants/me/btcpay/test');
      setTestResult(res.data);
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Could not run the connection test'));
    } finally {
      setTesting(false);
    }
  }

  async function openAuthorize() {
    setOpening(true);
    try {
      const res = await api.get<BtcPayAuthorizeUrl>('/tenants/me/btcpay/authorize-url');
      // The stored URL is the SERVER's route to BTCPay; rewrite
      // host.docker.internal so the operator's browser can actually open it.
      const browserUrl = toBrowserUrl(res.data.authorize_url, window.location.hostname);
      window.open(browserUrl, '_blank', 'noopener,noreferrer');
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Save the BTCPay server URL first'));
    } finally {
      setOpening(false);
    }
  }

  const urlHint = isDockerHostUrl(savedUrl) && trimmedUrl === savedUrl
    ? `Server-side address; links open via ${window.location.hostname} in your browser.`
    : 'The address OpenSplit’s server uses to reach BTCPay — must start with http:// or https://';

  return (
    <div className="p-6 sm:p-8">
      <div className="flex flex-wrap items-center gap-3">
        <PlugZap className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
        <h2 className="font-semibold text-[#F5F5F7]">BTCPay connection</h2>
        {/* Unconfigured is a setup state, not an error. */}
        <Badge variant={connected ? 'success' : configured ? 'error' : 'default'}>
          {connected ? 'Connected' : configured ? 'Disconnected' : 'Not connected'}
        </Badge>
      </div>
      <p className="mt-2 text-sm text-[#94A3B8]">
        OpenSplit reads settled invoices and sends split payouts through your own BTCPay Server.
        Nothing is custodied here.
      </p>

      {!configured && (
        <div className="mt-4 rounded-2xl border border-white/[0.10] bg-white/[0.03] px-4 py-3 text-sm text-[#94A3B8]">
          <span className="font-semibold text-[#F5F5F7]">Not connected yet.</span> Save your BTCPay
          server URL, create an API key with the minimal permissions using the button below, then
          paste the key and your store ID here.
        </div>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Input
            label="BTCPay server URL"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://your-btcpay-server.example"
            spellCheck={false}
            autoComplete="off"
            error={urlError}
            hint={urlHint}
          />
        </div>
        <Input
          label="Store ID"
          value={storeId}
          onChange={(event) => setStoreId(event.target.value)}
          placeholder="Your BTCPay store ID"
          spellCheck={false}
          autoComplete="off"
          maxLength={64}
          hint="Copy it from your BTCPay store settings."
        />
        <Input
          label="API key"
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={keySet ? `•••• ${keyLast4 ?? ''}`.trim() : 'Paste your BTCPay API key'}
          spellCheck={false}
          autoComplete="new-password"
          hint={
            keySet
              ? 'Greenfield API key — the stored value is never shown. Enter a new key to replace it.'
              : 'Greenfield API key — the stored value is never shown.'
          }
        />
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={openAuthorize}
            loading={opening}
            disabled={!savedUrl || opening}
            title={!savedUrl ? 'Save the server URL first' : undefined}
          >
            <ExternalLink className="h-4 w-4" strokeWidth={1.8} />
            Open BTCPay to create an API key
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={runTest}
            loading={testing}
            disabled={!configured || testing || dirty}
            title={
              dirty
                ? 'Save your changes first'
                : !configured
                  ? 'Save the server URL, store ID, and API key first'
                  : undefined
            }
          >
            Test connection
          </Button>
        </div>
        <div className="flex items-center gap-2 sm:shrink-0">
          {dirty && (
            <Button variant="ghost" size="sm" onClick={discardChanges} disabled={saving}>
              Discard
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={saveConnection} loading={saving} disabled={!canSave}>
            Save connection
          </Button>
        </div>
      </div>

      {!savedUrl && (
        <p className="mt-2 text-xs text-[#94A3B8]">
          The API-key button unlocks once the server URL is saved.
        </p>
      )}
      {dirty && (
        <p className="mt-2 text-xs font-medium text-orange-200">
          Unsaved changes — Test connection runs against the last saved values, so save your
          changes first (or discard them).
        </p>
      )}

      {testResult && (
        <div
          className={cn(
            'mt-5 rounded-2xl border p-4',
            testResult.ok
              ? 'border-emerald-300/20 bg-emerald-400/[0.06]'
              : 'border-red-300/20 bg-red-400/[0.06]',
            dirty && 'opacity-60'
          )}
        >
          {dirty && (
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-orange-200">
              Stale — settings changed after this test ran
            </p>
          )}
          <ul className="space-y-2.5">
            <CheckRow label="Server reachable" state={testResult.url_reachable} />
            <CheckRow label="API key valid" state={testResult.auth_ok} />
            <CheckRow label="Store found" state={testResult.store_found} />
          </ul>
          <p
            className={cn(
              'mt-3 text-sm',
              testResult.ok ? 'text-emerald-300' : 'text-red-300'
            )}
          >
            {testResult.detail}
          </p>
        </div>
      )}
    </div>
  );
}
