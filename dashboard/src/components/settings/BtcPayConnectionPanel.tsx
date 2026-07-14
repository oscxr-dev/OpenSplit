import { useEffect, useState } from 'react';
import axios from 'axios';
import { Check, ExternalLink, Minus, PlugZap, X } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const status =
    state === null
      ? t('settings.btcpay.notChecked')
      : state
        ? t('settings.btcpay.checkPassed')
        : t('settings.btcpay.checkFailed');
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
      {state === null && <span className="text-xs text-[#94A3B8]">{t('settings.btcpay.notChecked')}</span>}
    </li>
  );
}

export function BtcPayConnectionPanel() {
  const { t } = useTranslation();
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
      ? t('settings.btcpay.urlError')
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
      toast.success(t('settings.btcpay.saved'));
    } catch (error) {
      toast.error(apiErrorMessage(error, t('settings.btcpay.saveError')));
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
      toast.error(apiErrorMessage(error, t('settings.btcpay.testError')));
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
      toast.error(apiErrorMessage(error, t('settings.btcpay.authorizeError')));
    } finally {
      setOpening(false);
    }
  }

  const urlHint = isDockerHostUrl(savedUrl) && trimmedUrl === savedUrl
    ? t('settings.btcpay.urlHintDocker', { hostname: window.location.hostname })
    : t('settings.btcpay.urlHint');

  return (
    <div className="p-6 sm:p-8">
      <div className="flex flex-wrap items-center gap-3">
        <PlugZap className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
        <h2 className="font-semibold text-[#F5F5F7]">{t('settings.btcpay.title')}</h2>
        {/* Unconfigured is a setup state, not an error. */}
        <Badge variant={connected ? 'success' : configured ? 'error' : 'default'}>
          {connected ? t('settings.btcpay.connected') : configured ? t('settings.btcpay.disconnected') : t('settings.btcpay.notConnected')}
        </Badge>
      </div>
      <p className="mt-2 text-sm text-[#94A3B8]">
        {t('settings.btcpay.description')}
      </p>

      {!configured && (
        <div className="mt-4 rounded-2xl border border-white/[0.10] bg-white/[0.03] px-4 py-3 text-sm text-[#94A3B8]">
          <span className="font-semibold text-[#F5F5F7]">{t('settings.btcpay.setupCtaTitle')}</span>{' '}
          {t('settings.btcpay.setupCtaBody')}
        </div>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Input
            label={t('settings.btcpay.serverUrl')}
            id="btcpay-server-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder={t('settings.btcpay.urlPlaceholder')}
            spellCheck={false}
            autoComplete="off"
            error={urlError}
            hint={urlHint}
          />
        </div>
        <Input
          label={t('settings.btcpay.storeId')}
          id="btcpay-store-id"
          value={storeId}
          onChange={(event) => setStoreId(event.target.value)}
          placeholder={t('settings.btcpay.storeIdPlaceholder')}
          spellCheck={false}
          autoComplete="off"
          maxLength={64}
          hint={t('settings.btcpay.storeIdHint')}
        />
        <Input
          label={t('settings.btcpay.apiKey')}
          id="btcpay-api-key"
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={keySet ? `•••• ${keyLast4 ?? ''}`.trim() : t('settings.btcpay.apiKeyPlaceholder')}
          spellCheck={false}
          autoComplete="new-password"
          hint={keySet ? t('settings.btcpay.apiKeyHintReplace') : t('settings.btcpay.apiKeyHint')}
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
            title={!savedUrl ? t('settings.btcpay.saveUrlFirst') : undefined}
          >
            <ExternalLink className="h-4 w-4" strokeWidth={1.8} />
            {t('settings.btcpay.openBtcpay')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={runTest}
            loading={testing}
            disabled={!configured || testing || dirty}
            title={
              dirty
                ? t('settings.btcpay.saveChangesFirst')
                : !configured
                  ? t('settings.btcpay.saveAllFirst')
                  : undefined
            }
          >
            {t('settings.btcpay.testConnection')}
          </Button>
        </div>
        <div className="flex items-center gap-2 sm:shrink-0">
          {dirty && (
            <Button variant="ghost" size="sm" onClick={discardChanges} disabled={saving}>
              {t('settings.btcpay.discard')}
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={saveConnection} loading={saving} disabled={!canSave}>
            {t('settings.btcpay.saveConnection')}
          </Button>
        </div>
      </div>

      {!savedUrl && (
        <p className="mt-2 text-xs text-[#94A3B8]">
          {t('settings.btcpay.unlockHint')}
        </p>
      )}
      {dirty && (
        <p className="mt-2 text-xs font-medium text-orange-200">
          {t('settings.btcpay.unsavedChanges')}
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
              {t('settings.btcpay.stale')}
            </p>
          )}
          <ul className="space-y-2.5">
            <CheckRow label={t('settings.btcpay.serverReachable')} state={testResult.url_reachable} />
            <CheckRow label={t('settings.btcpay.apiKeyValid')} state={testResult.auth_ok} />
            <CheckRow label={t('settings.btcpay.storeFound')} state={testResult.store_found} />
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
