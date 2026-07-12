import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Check, Coins, Globe2, Info, KeyRound, Link2, LogOut, MapPin, Moon, ShieldCheck, Store, Sun } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Input } from '@/components/ui/Input';
import { BtcPayConnectionPanel } from '@/components/settings/BtcPayConnectionPanel';
import { BtcPayWebhookPanel } from '@/components/settings/BtcPayWebhookPanel';
import { StatusStrip } from '@/components/team/StatusStrip';
import { useAuth } from '@/hooks/useAuth';
import { useSplits, useToggleSplitPublic } from '@/hooks/useSplits';
import { useTheme } from '@/hooks/useTheme';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import type { SplitRule, TenantResponse } from '@/types/api';

const themeOptions = [
  {
    value: 'dark' as const,
    label: 'Dark',
    description: 'Deep surfaces for the proof canvas.',
    icon: Moon,
  },
  {
    value: 'light' as const,
    label: 'Light',
    description: 'A brighter shell with strong contrast.',
    icon: Sun,
  },
];

// Client-side tabs, deep-linkable via the URL hash (/settings#public-page).
const SETTINGS_TABS = [
  { id: 'connection', label: 'Connection' },
  { id: 'store', label: 'Store' },
  { id: 'public-page', label: 'Public page' },
  { id: 'appearance', label: 'Appearance' },
] as const;

type SettingsTabId = (typeof SETTINGS_TABS)[number]['id'];

function tabFromHash(hash: string): SettingsTabId {
  const id = hash.replace(/^#/, '');
  return SETTINGS_TABS.some((tab) => tab.id === id) ? (id as SettingsTabId) : 'connection';
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function InfoTip({ children }: { children: string }) {
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="group inline-flex h-5 w-5 items-center justify-center rounded-full border border-[#94A3B8]/35 text-[#94A3B8] transition hover:border-[#FF2D78]/45 hover:text-[#FF2D78] focus:outline-none focus:ring-2 focus:ring-[#FF2D78]/20"
        aria-label={children}
      >
        <Info className="h-3.5 w-3.5" strokeWidth={2} />
        <span className="pointer-events-none absolute left-1/2 top-7 z-20 w-64 -translate-x-1/2 rounded-lg border border-white/[0.10] bg-[#11131F] px-3 py-2 text-left text-xs font-medium leading-5 text-[#F5F5F7] opacity-0 shadow-[0_18px_50px_rgba(0,0,0,0.22)] transition group-hover:opacity-100 group-focus:opacity-100">
          {children}
        </span>
      </button>
    </span>
  );
}

function activeTargets(rule?: SplitRule | null) {
  return (rule?.targets ?? []).filter((target) => target.percentage > 0);
}

function allocationTotal(rule?: SplitRule | null) {
  return activeTargets(rule).reduce((sum, target) => sum + target.percentage, 0);
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { logout, tenant, refreshTenant } = useAuth();
  const { data: splitRules = [], isLoading: splitRulesLoading } = useSplits();
  const toggleSplitPublic = useToggleSplitPublic();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirmPublicProofOpen, setConfirmPublicProofOpen] = useState(false);
  const [savingPublicProof, setSavingPublicProof] = useState(false);
  const [confirmShowAmountsOpen, setConfirmShowAmountsOpen] = useState(false);
  const [savingShowAmounts, setSavingShowAmounts] = useState(false);
  const [showPublicRulesOnly, setShowPublicRulesOnly] = useState(false);
  // Display name comes from tenant.name only — brand_display_name is a dormant
  // column and must not surface anywhere (stale "BitCrew" branding, P-F).
  const publicSlug = tenant?.tenant.public_slug || slugify(tenant?.tenant.name || 'OpenSplit');
  const publicPageOn = Boolean(tenant?.tenant.public_transparency_enabled);
  const showAmountsOn = Boolean(tenant?.tenant.public_show_amounts);
  const publicRules = splitRules.filter((rule) => rule.public_enabled);
  const displayedPublicRules = showPublicRulesOnly ? publicRules : splitRules;

  const [activeTab, setActiveTab] = useState<SettingsTabId>(() => tabFromHash(window.location.hash));
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    const onHashChange = () => setActiveTab(tabFromHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  function selectTab(id: SettingsTabId) {
    setActiveTab(id);
    window.history.replaceState(null, '', `#${id}`);
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = (index + 1) % SETTINGS_TABS.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = SETTINGS_TABS.length - 1;
    if (next === null) return;
    event.preventDefault();
    selectTab(SETTINGS_TABS[next].id);
    tabRefs.current[next]?.focus();
  }

  function tabPanelProps(id: SettingsTabId) {
    return {
      role: 'tabpanel' as const,
      id: `settings-panel-${id}`,
      'aria-labelledby': `settings-tab-${id}`,
    };
  }

  async function refreshSettingsDependents(previousSlug?: string | null, nextSlug?: string | null) {
    await refreshTenant();
    await queryClient.invalidateQueries({ queryKey: ['tenant'] });
    await queryClient.invalidateQueries({ queryKey: ['public-teams'] });
    await queryClient.invalidateQueries({ queryKey: ['settings'] });
    if (previousSlug) {
      await queryClient.invalidateQueries({ queryKey: ['public-transparency', previousSlug] });
      queryClient.removeQueries({ queryKey: ['public-transparency', previousSlug] });
    }
    if (nextSlug) {
      await queryClient.invalidateQueries({ queryKey: ['public-transparency', nextSlug] });
    }
  }

  async function patchTenantSettings(
    payload: Partial<TenantResponse>,
    options: { success: string; previousSlug?: string | null; nextSlug?: string | null }
  ) {
    const response = await api.patch<TenantResponse>('/tenants/me', payload);
    await refreshSettingsDependents(options.previousSlug, options.nextSlug ?? response.data.public_slug);
    toast.success(options.success);
    return response.data;
  }

  // Editable store/team name (tenant.name). Saved via the existing PATCH
  // /tenants/me, then refreshed so the new name propagates across the app.
  const currentName = tenant?.tenant.name ?? '';
  const [storeName, setStoreName] = useState(currentName);
  const [savingName, setSavingName] = useState(false);
  useEffect(() => {
    setStoreName(currentName);
  }, [currentName]);

  const trimmedName = storeName.trim();
  const nameDirty = trimmedName.length > 0 && trimmedName !== currentName;

  async function saveStoreName() {
    if (!nameDirty) return;
    setSavingName(true);
    try {
      await patchTenantSettings(
        { name: trimmedName },
        { success: 'Store name updated', nextSlug: savedSlug }
      );
    } catch {
      toast.error('Could not update store name');
    } finally {
      setSavingName(false);
    }
  }

  // Public URL slug (tenant.public_slug) — separate from the store name. Once a
  // slug is saved we keep it (don't re-derive from the name); only fall back to
  // a name-derived slug while none has been saved yet.
  const savedSlug = tenant?.tenant.public_slug ?? '';
  const [slugInput, setSlugInput] = useState(savedSlug || slugify(currentName));
  const [savingSlug, setSavingSlug] = useState(false);
  useEffect(() => {
    setSlugInput(savedSlug || slugify(currentName));
  }, [savedSlug, currentName]);

  const normalizedSlug = slugify(slugInput);
  const slugDirty = normalizedSlug.length > 0 && normalizedSlug !== savedSlug;

  async function savePublicSlug() {
    if (!slugDirty) return;
    setSavingSlug(true);
    try {
      await patchTenantSettings(
        { public_slug: normalizedSlug },
        {
          success: 'Public URL updated',
          previousSlug: savedSlug,
          nextSlug: normalizedSlug,
        }
      );
    } catch {
      toast.error('Could not update public URL');
    } finally {
      setSavingSlug(false);
    }
  }

  // Optional, coarse public location for the Public Teams map (country/city only;
  // never a precise address). Blank clears it ("Unknown location").
  const currentCountry = tenant?.tenant.public_country ?? '';
  const currentCity = tenant?.tenant.public_city ?? '';
  const [country, setCountry] = useState(currentCountry);
  const [city, setCity] = useState(currentCity);
  const [savingLocation, setSavingLocation] = useState(false);
  useEffect(() => {
    setCountry(currentCountry);
    setCity(currentCity);
  }, [currentCountry, currentCity]);

  const locationDirty = country.trim() !== currentCountry || city.trim() !== currentCity;

  async function saveLocation() {
    if (!locationDirty) return;
    setSavingLocation(true);
    try {
      await patchTenantSettings(
        { public_country: country.trim(), public_city: city.trim() },
        { success: 'Location updated', nextSlug: savedSlug }
      );
    } catch {
      toast.error('Could not update location');
    } finally {
      setSavingLocation(false);
    }
  }

  async function savePublicProof(nextValue: boolean) {
    if (nextValue === publicPageOn) return;
    setSavingPublicProof(true);
    try {
      await patchTenantSettings(
        { public_transparency_enabled: nextValue },
        {
          success: nextValue ? 'Public proof enabled' : 'Public proof disabled',
          nextSlug: savedSlug,
        }
      );
    } catch {
      toast.error('Could not update public proof');
    } finally {
      setSavingPublicProof(false);
      setConfirmPublicProofOpen(false);
    }
  }

  // Amounts on the public page (tenant.public_show_amounts). Off by default and
  // privacy-safe: visitors see split percentages and activity, never sat amounts
  // or totals. Turning it ON is the only privacy-loosening move, so it requires
  // explicit confirmation; turning it OFF re-hides immediately.
  async function saveShowAmounts(nextValue: boolean) {
    if (nextValue === showAmountsOn) return;
    setSavingShowAmounts(true);
    try {
      await patchTenantSettings(
        { public_show_amounts: nextValue },
        {
          success: nextValue ? 'Amounts now visible on the public page' : 'Amounts hidden on the public page',
          nextSlug: savedSlug,
        }
      );
    } catch {
      toast.error('Could not update amount visibility');
    } finally {
      setSavingShowAmounts(false);
      setConfirmShowAmountsOpen(false);
    }
  }

  // Team Nostr signing identity — the PUBLIC key signed proofs verify against.
  // Lives on the Public page tab because it is public verification identity
  // (like the slug), not store plumbing. The private key never passes through
  // the browser: the server signs with its ORCHESTRATOR_NOSTR_SECKEY env var.
  const savedNostrNpub = tenant?.tenant.nostr_npub ?? '';
  const [nostrKeyInput, setNostrKeyInput] = useState(savedNostrNpub);
  const [savingNostrKey, setSavingNostrKey] = useState(false);
  useEffect(() => {
    setNostrKeyInput(savedNostrNpub);
  }, [savedNostrNpub]);

  const nostrKeyDirty = nostrKeyInput.trim() !== savedNostrNpub;

  async function saveNostrKey() {
    if (!nostrKeyDirty) return;
    const trimmed = nostrKeyInput.trim();
    // Defense in depth: the backend rejects nsec too, but a private key must
    // not even leave the browser in a request body.
    if (trimmed.toLowerCase().startsWith('nsec')) {
      toast.error('That is a PRIVATE key (nsec) — never paste it here. Enter your public npub instead.');
      return;
    }
    setSavingNostrKey(true);
    try {
      // A blank value explicitly clears the saved key.
      await patchTenantSettings(
        { nostr_pubkey: trimmed },
        { success: trimmed ? 'Nostr public key saved' : 'Nostr public key removed', nextSlug: savedSlug }
      );
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail) && typeof detail[0]?.msg === 'string'
            ? detail[0].msg
            : 'Could not save the Nostr public key'
      );
    } finally {
      setSavingNostrKey(false);
    }
  }

  async function toggleRulePublic(rule: SplitRule) {
    if (!publicPageOn) {
      toast.error('Turn Public proof on before publishing rules');
      return;
    }

    try {
      await toggleSplitPublic.mutateAsync({
        id: rule.id,
        public_enabled: !rule.public_enabled,
        slug: publicSlug,
      });
      toast.success(!rule.public_enabled ? 'Rule is public' : 'Rule hidden from public page');
    } catch {
      toast.error('Could not update public rule');
    }
  }

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <div
          role="tablist"
          aria-label="Settings sections"
          className="flex w-max min-w-full gap-1 rounded-full border border-white/[0.08] bg-white/[0.035] p-1 sm:w-full"
        >
          {SETTINGS_TABS.map((tab, index) => {
            const selected = activeTab === tab.id;

            return (
              <button
                key={tab.id}
                ref={(el) => {
                  tabRefs.current[index] = el;
                }}
                type="button"
                role="tab"
                id={`settings-tab-${tab.id}`}
                aria-selected={selected}
                aria-controls={`settings-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => selectTab(tab.id)}
                onKeyDown={(event) => onTabKeyDown(event, index)}
                className={cn(
                  'min-h-10 shrink-0 grow whitespace-nowrap rounded-full px-4 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#FF2D78]/30',
                  selected
                    ? 'bg-[#FF2D78] text-white'
                    : 'text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                )}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === 'connection' && (
        <div {...tabPanelProps('connection')} className="space-y-6">
          <div className="space-y-3">
            <h2 className="font-semibold text-[#F5F5F7]">Pipeline status</h2>
            <StatusStrip />
          </div>

          <Card>
            <CardContent className="p-0">
              <BtcPayConnectionPanel />

              <div className="border-t border-white/[0.07]">
                <BtcPayWebhookPanel />
              </div>

              <div className="border-t border-white/[0.07] p-6 sm:p-8">
                {/* Privacy: the tenant UUID stays collapsed by default — only shown on demand. */}
                <details>
                  <summary className="cursor-pointer select-none text-xs font-medium text-[#94A3B8] transition hover:text-[#F5F5F7]">
                    Advanced
                  </summary>
                  <p className="mt-1 font-mono text-xs text-[#94A3B8]">
                    Workspace ID: {tenant?.tenant.id ?? 'workspace pending'}
                  </p>
                </details>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'store' && (
        <div {...tabPanelProps('store')}>
          <Card>
            <CardContent className="p-0">
              <div className="p-6 sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:items-end sm:justify-between sm:text-left">
                  <div className="w-full sm:max-w-sm">
                    <div className="flex items-center justify-center gap-3 sm:justify-start">
                      <Store className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                      <h2 className="font-semibold text-[#F5F5F7]">Store name</h2>
                      <InfoTip>
                        The display name shown inside OpenSplit and on the public proof page. It does not change historical Split Proof records.
                      </InfoTip>
                    </div>
                    <Input
                      className="mt-4"
                      value={storeName}
                      onChange={(event) => setStoreName(event.target.value)}
                      placeholder="Your team"
                      aria-label="Store or team name"
                      maxLength={255}
                    />
                  </div>
                  <Button variant="primary" size="sm" onClick={saveStoreName} loading={savingName} disabled={!nameDirty} className="shrink-0">
                    Save name
                  </Button>
                </div>
              </div>

              <div className="border-t border-white/[0.07] p-6 sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:items-end sm:justify-between sm:text-left">
                  <div className="w-full sm:max-w-sm">
                    <div className="flex items-center justify-center gap-3 sm:justify-start">
                      <Link2 className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                      <h2 className="font-semibold text-[#F5F5F7]">Public URL</h2>
                      <InfoTip>
                        The stable public link for this team. Keep it short and readable so visitors can verify payment proofs later.
                      </InfoTip>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <span className="shrink-0 font-mono text-sm text-[#94A3B8]">/public/</span>
                      <Input
                        value={slugInput}
                        onChange={(event) => setSlugInput(event.target.value)}
                        placeholder="your-team"
                        aria-label="Public URL slug"
                        maxLength={120}
                        spellCheck={false}
                      />
                    </div>
                    <p className="mt-2 font-mono text-xs text-[#94A3B8]">
                      Opens at <span className="text-[#F5F5F7]">/public/{normalizedSlug || 'your-store'}</span>
                    </p>
                  </div>
                  <Button variant="primary" size="sm" onClick={savePublicSlug} loading={savingSlug} disabled={!slugDirty} className="shrink-0">
                    Save URL
                  </Button>
                </div>
              </div>

              <div className="border-t border-white/[0.07] p-6 sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:items-end sm:justify-between sm:text-left">
                  <div className="w-full sm:max-w-md">
                    <div className="flex items-center justify-center gap-3 sm:justify-start">
                      <MapPin className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                      <h2 className="font-semibold text-[#F5F5F7]">Public location</h2>
                      <InfoTip>
                        Optional. Shown on the Public Teams map at country level only — never a precise address or coordinates. Leave blank to stay under &quot;Unknown location&quot;.
                      </InfoTip>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <Input
                        value={country}
                        onChange={(event) => setCountry(event.target.value)}
                        placeholder="Country (e.g. Spain)"
                        aria-label="Public country"
                        maxLength={80}
                      />
                      <Input
                        value={city}
                        onChange={(event) => setCity(event.target.value)}
                        placeholder="City (optional)"
                        aria-label="Public city"
                        maxLength={120}
                      />
                    </div>
                  </div>
                  <Button variant="primary" size="sm" onClick={saveLocation} loading={savingLocation} disabled={!locationDirty} className="shrink-0">
                    Save location
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'public-page' && (
        <div {...tabPanelProps('public-page')}>
          <Card>
            <CardContent className="p-0">
              <div className="p-6 sm:p-8">
                <div className="rounded-3xl border border-white/[0.08] bg-white/[0.025] p-5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-6">
                  <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between sm:text-left">
                    <div>
                      <div className="flex items-center justify-center gap-3 sm:justify-start">
                        <ShieldCheck className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                        <h2 className="font-semibold text-[#F5F5F7]">Public proof</h2>
                        <InfoTip>
                          Enables the public proof page. Each split rule still needs its own Public toggle before it appears there.
                        </InfoTip>
                      </div>
                      <p className="mt-3 font-mono text-xs text-[#94A3B8]">/public/{publicSlug}</p>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        if (publicPageOn) {
                          void savePublicProof(false);
                          return;
                        }

                        setConfirmPublicProofOpen(true);
                      }}
                      className={cn(
                        'public-proof-master-toggle inline-flex min-h-10 min-w-24 items-center justify-center rounded-full border px-5 text-sm font-semibold transition',
                        publicPageOn
                          ? 'public-toggle-on border-orange-300/50 bg-orange-500 text-white shadow-[0_0_0_4px_rgba(249,115,22,0.10)]'
                          : 'border-white/[0.16] bg-white text-[#11131F] hover:bg-white/90'
                      )}
                      aria-pressed={publicPageOn}
                      disabled={savingPublicProof}
                    >
                      {publicPageOn ? 'On' : 'Off'}
                    </button>
                  </div>

                  <div
                    className={cn(
                      'public-rules-panel mt-5 rounded-2xl border p-3 transition sm:p-4',
                      publicPageOn
                        ? 'public-rules-panel-on border-white/[0.10] bg-[#181A26]/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]'
                        : 'public-rules-panel-off border-white/[0.08] bg-[#181A26]/38 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]'
                    )}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-center justify-center gap-3 sm:justify-start">
                        <div
                          className={cn(
                            'public-rules-icon flex h-9 w-9 items-center justify-center rounded-xl text-[#FF2D78]',
                            publicPageOn ? 'bg-[#FF2D78]/14' : 'bg-white/[0.06]'
                          )}
                        >
                          <Globe2 className="h-4.5 w-4.5" strokeWidth={1.8} />
                        </div>
                        <div className="text-center sm:text-left">
                          <p className="text-sm font-semibold text-[#F5F5F7]">Public rules</p>
                          <p className="mt-1 font-mono text-xs text-[#94A3B8]">
                            {publicPageOn
                              ? `${publicRules.length} public · ${splitRules.length} total`
                              : `Off · ${publicRules.length} saved public · ${splitRules.length} total`}
                          </p>
                        </div>
                      </div>

                      <div className="public-rules-filter mx-auto grid w-full max-w-xs grid-cols-2 gap-1 rounded-full border border-white/[0.08] bg-white/[0.035] p-1 sm:mx-0">
                        <button
                          type="button"
                          onClick={() => setShowPublicRulesOnly(true)}
                          className={cn(
                            'rounded-full px-3 py-2 text-xs font-semibold transition',
                            showPublicRulesOnly
                              ? 'bg-[#FF2D78] text-white'
                              : 'text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                          )}
                        >
                          Public only
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowPublicRulesOnly(false)}
                          className={cn(
                            'rounded-full px-3 py-2 text-xs font-semibold transition',
                            !showPublicRulesOnly
                              ? 'bg-[#FF2D78] text-white'
                              : 'text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                          )}
                        >
                          All rules
                        </button>
                      </div>
                    </div>

                    {!publicPageOn && (
                      <div className="public-rules-paused mt-4 rounded-2xl border border-orange-300/20 bg-orange-400/[0.08] px-4 py-3 text-sm font-medium text-orange-100">
                        Public proof is Off. Saved public-rule choices are paused and hidden from visitors.
                      </div>
                    )}

                    <div className="public-rules-list mt-4 overflow-hidden rounded-2xl border border-white/[0.10] bg-[#11131F]/52">
                      {splitRulesLoading && (
                        <p className="p-4 text-sm text-[#94A3B8]">Loading rules...</p>
                      )}

                      {!splitRulesLoading && displayedPublicRules.length === 0 && (
                        <p className="p-4 text-sm text-[#94A3B8]">
                          {showPublicRulesOnly ? 'No public rules yet.' : 'No split rules yet.'}
                        </p>
                      )}

                      {!splitRulesLoading &&
                        displayedPublicRules.map((rule) => {
                          const wallets = activeTargets(rule).length;
                          const total = allocationTotal(rule);
                          const busy = toggleSplitPublic.isPending;
                          const toggleDisabled = busy || !publicPageOn;

                          return (
                            <div
                              key={rule.id}
                              className={cn(
                                'public-rule-row grid gap-3 border-b border-white/[0.07] p-4 text-left transition last:border-b-0 lg:grid-cols-[minmax(180px,1fr)_auto_auto]',
                                publicPageOn
                                  ? 'bg-[#151722]/82 hover:bg-[#181A26]'
                                  : 'bg-[#151722]/48'
                              )}
                            >
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="truncate text-sm font-semibold text-[#F5F5F7]">{rule.name}</p>
                                  <Badge variant={rule.active ? 'success' : 'default'}>{rule.active ? 'Active' : 'Inactive'}</Badge>
                                </div>
                                <p className="mt-2 font-mono text-xs text-[#94A3B8]">
                                  v{rule.version} · {wallets} wallets · {total}% allocated
                                </p>
                              </div>

                              <div className="flex items-center gap-2 lg:justify-end">
                                <span className="text-xs font-semibold text-[#94A3B8]">Public</span>
                                <button
                                  type="button"
                                  onClick={() => void toggleRulePublic(rule)}
                                  disabled={toggleDisabled}
                                  aria-pressed={publicPageOn && rule.public_enabled}
                                  title={!publicPageOn ? 'Turn Public proof on before publishing rules' : undefined}
                                  className={cn(
                                    'public-rule-toggle relative h-8 w-16 rounded-full border transition focus:outline-none focus:ring-2 focus:ring-[#FF2D78]/30',
                                    toggleDisabled && 'cursor-not-allowed',
                                    publicPageOn && rule.public_enabled
                                      ? 'border-[#FF2D78]/55 bg-[#FF2D78]'
                                      : 'border-white/[0.16] bg-white/[0.08]',
                                    !publicPageOn && rule.public_enabled && 'border-orange-300/28 bg-orange-400/[0.12]'
                                  )}
                                >
                                  <span
                                    className={cn(
                                      'absolute top-1 h-6 w-6 rounded-full bg-white shadow transition',
                                      rule.public_enabled ? 'left-9' : 'left-1',
                                      !publicPageOn && 'bg-white/75'
                                    )}
                                  />
                                  <span className="sr-only">
                                    {rule.public_enabled ? 'Hide rule from public page' : 'Show rule on public page'}
                                  </span>
                                </button>
                              </div>

                              <p className={cn(
                                'self-center font-mono text-xs font-semibold lg:text-right',
                                publicPageOn && rule.public_enabled
                                  ? 'text-[#FF2D78]'
                                  : rule.public_enabled
                                    ? 'text-orange-200'
                                    : 'text-[#94A3B8]'
                              )}>
                                {publicPageOn ? (rule.public_enabled ? 'ON' : 'OFF') : (rule.public_enabled ? 'PAUSED' : 'OFF')}
                              </p>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                </div>
              </div>

              <div className="border-t border-white/[0.07] p-6 sm:p-8">
                <div
                  className={cn(
                    'public-amounts-panel rounded-3xl border p-5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition sm:p-6',
                    publicPageOn
                      ? 'border-white/[0.08] bg-white/[0.025]'
                      : 'public-amounts-panel-off border-white/[0.06] bg-white/[0.015]'
                  )}
                >
                  <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between sm:text-left">
                    <div>
                      <div className="flex items-center justify-center gap-3 sm:justify-start">
                        <Coins className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                        <h2 className="font-semibold text-[#F5F5F7]">Show amounts on the public page</h2>
                        <InfoTip>
                          Off by default. When off, visitors see split percentages and activity, never sat amounts or your total sats moved.
                        </InfoTip>
                      </div>
                      <p className="mt-3 max-w-md text-sm leading-6 text-[#94A3B8]">
                        {showAmountsOn
                          ? 'On — every public visitor can see the sat amount of each payment and your total sats moved.'
                          : 'Off — visitors see split percentages and activity, never sat amounts or totals.'}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        if (!publicPageOn) return;
                        if (showAmountsOn) {
                          void saveShowAmounts(false);
                          return;
                        }
                        setConfirmShowAmountsOpen(true);
                      }}
                      className={cn(
                        'public-amounts-toggle inline-flex min-h-10 min-w-24 items-center justify-center rounded-full border px-5 text-sm font-semibold transition',
                        !publicPageOn && 'cursor-not-allowed',
                        publicPageOn && showAmountsOn
                          ? 'public-amounts-toggle-on border-orange-300/50 bg-orange-500 text-white shadow-[0_0_0_4px_rgba(249,115,22,0.10)]'
                          : publicPageOn
                            ? 'border-white/[0.16] bg-white text-[#11131F] hover:bg-white/90'
                            : 'border-white/[0.10] bg-white/[0.06] text-[#94A3B8]'
                      )}
                      aria-pressed={publicPageOn && showAmountsOn}
                      aria-label="Show amounts on the public page"
                      disabled={!publicPageOn || savingShowAmounts}
                      title={!publicPageOn ? 'Turn Public proof on first' : undefined}
                    >
                      {showAmountsOn ? 'On' : 'Off'}
                    </button>
                  </div>

                  {!publicPageOn && (
                    <div className="public-amounts-paused mt-4 rounded-2xl border border-orange-300/20 bg-orange-400/[0.08] px-4 py-3 text-sm font-medium text-orange-100">
                      Public proof is Off. Amount visibility is paused — turn Public proof on to change it.
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-white/[0.07] p-6 sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:items-end sm:justify-between sm:text-left">
                  <div className="w-full sm:max-w-md">
                    <div className="flex items-center justify-center gap-3 sm:justify-start">
                      <KeyRound className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                      <h2 className="font-semibold text-[#F5F5F7]">Nostr signing identity</h2>
                      <InfoTip>
                        The team’s PUBLIC key (npub or hex) that signed Split Proofs verify against. The private signing key stays on your server as ORCHESTRATOR_NOSTR_SECKEY — OpenSplit never stores it. Never paste an nsec here.
                      </InfoTip>
                    </div>
                    <Input
                      className="mt-4 font-mono"
                      value={nostrKeyInput}
                      onChange={(event) => setNostrKeyInput(event.target.value)}
                      placeholder="npub1…"
                      aria-label="Team Nostr public key"
                      maxLength={128}
                      spellCheck={false}
                    />
                    <p className="mt-2 break-all font-mono text-xs text-[#94A3B8]">
                      {savedNostrNpub ? (
                        <>
                          Saved: <span className="text-[#F5F5F7]">{savedNostrNpub}</span>
                        </>
                      ) : (
                        'No key saved — the Sign proof action stays hidden on receipts.'
                      )}
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={saveNostrKey}
                    loading={savingNostrKey}
                    disabled={!nostrKeyDirty}
                    className="shrink-0"
                  >
                    Save key
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'appearance' && (
        <div {...tabPanelProps('appearance')}>
          <Card>
            <CardContent className="p-0">
              <div className="p-6 sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:items-center sm:justify-between sm:text-left">
                  <div>
                    <div className="flex items-center justify-center gap-3 sm:justify-start">
                      <h2 className="font-semibold text-[#F5F5F7]">Appearance</h2>
                      <InfoTip>
                        Sets the interface theme for this browser only. Payment records, Split Proofs, and public data stay unchanged.
                      </InfoTip>
                    </div>
                  </div>

                  <div className="grid w-full max-w-xs grid-cols-2 gap-2 rounded-lg border border-white/[0.08] bg-white/[0.035] p-1.5">
                    {themeOptions.map((option) => {
                      const selected = theme === option.value;

                      return (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => setTheme(option.value)}
                          className={cn(
                            'relative inline-flex min-h-10 items-center justify-center gap-2 rounded-md text-sm font-semibold transition',
                            selected
                              ? 'bg-[#FF2D78] text-[#0A0B12]'
                              : 'text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                          )}
                          title={option.description}
                        >
                          <option.icon className="h-4 w-4" strokeWidth={1.8} />
                          {option.label}
                          {selected && <Check className="absolute right-2 h-3.5 w-3.5" strokeWidth={2} />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={confirmPublicProofOpen}
        logoSrc="/brand/OpenSplit-navbar.svg"
        title="Enable public proof?"
        description="Only the rules you publish will be visible. Private wallet data stays hidden."
        cancelLabel="Cancel"
        confirmLabel="Enable"
        celebrateOnConfirm
        loading={savingPublicProof}
        confirmDisabled={savingPublicProof}
        onClose={() => setConfirmPublicProofOpen(false)}
        onConfirm={() => {
          void savePublicProof(true);
        }}
      >
        <div className="public-proof-confirm-summary mx-auto flex max-w-[18rem] items-center justify-between gap-3 rounded-2xl border border-white/[0.12] bg-white/[0.045] px-4 py-3 text-left">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#FF2D78]">Visible rules</p>
            <p className="mt-0.5 text-sm font-semibold text-white">{publicRules.length} selected</p>
          </div>
          <span className="rounded-full bg-[#FF2D78]/12 px-3 py-1 text-xs font-semibold text-[#FF2D78]">Public</span>
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmShowAmountsOpen}
        logoSrc="/brand/OpenSplit-navbar.svg"
        title="Show amounts publicly?"
        description="This makes every public visitor able to see the sat amount of each payment and your total sats moved. Continue?"
        cancelLabel="Cancel"
        confirmLabel="Show amounts"
        loading={savingShowAmounts}
        confirmDisabled={savingShowAmounts}
        onClose={() => setConfirmShowAmountsOpen(false)}
        onConfirm={() => {
          void saveShowAmounts(true);
        }}
      />

      <Button
        variant="ghost"
        onClick={() => {
          logout();
          navigate('/login');
        }}
      >
        <LogOut className="h-4 w-4" strokeWidth={1.8} />
        Sign out
      </Button>
    </div>
  );
}
