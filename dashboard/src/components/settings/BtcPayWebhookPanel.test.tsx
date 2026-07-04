// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { TenantHealth } from '@/types/api';

// jsdom does not implement <dialog> methods used by ConfirmDialog.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
  };
});

const authState = vi.hoisted(() => ({
  tenant: null as TenantHealth | null,
  refreshTenant: vi.fn(),
}));

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ tenant: authState.tenant, refreshTenant: authState.refreshTenant }),
}));
vi.mock('@/lib/api', () => ({ default: apiMock }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { BtcPayWebhookPanel } from './BtcPayWebhookPanel';

const SECRET = 'gen-secret-URLSAFE_abcdefghijklmnopqrstuvwxyz';
const WEBHOOK_URL = 'http://host.docker.internal:8000/api/v1/webhooks/btcpay/tenant-1';

function makeTenant(overrides: Partial<TenantHealth['tenant']> = {}): TenantHealth {
  return {
    tenant: {
      id: 'tenant-1',
      name: 'Coffee Co',
      adapter_type: 'btcpay',
      lnbits_url: null,
      brand_display_name: null,
      brand_color: null,
      brand_logo_url: null,
      public_slug: 'coffee',
      public_transparency_enabled: false,
      btcpay_url: 'https://btcpay.local',
      btcpay_store_id: 'store-1',
      btcpay_api_key_set: true,
      btcpay_api_key_last4: '9F3A',
      btcpay_webhook_secret_set: false,
      last_webhook_at: null,
      active: true,
      created_at: '2026-01-01T00:00:00Z',
      ...overrides,
    },
    connection_status: 'ok',
    lnbits_status: 'ok',
  };
}

function mockGenerateResponse() {
  apiMock.post.mockResolvedValueOnce({
    data: {
      secret: SECRET,
      webhook_url: WEBHOOK_URL,
      events: ['InvoiceSettled', 'InvoicePaymentSettled'],
    },
  });
}

/** Assert `text` never appears in any DOM text node. */
function expectTextAbsent(container: HTMLElement, text: string) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    expect(walker.currentNode.textContent).not.toContain(text);
  }
}

beforeEach(() => {
  authState.refreshTenant = vi.fn().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('BtcPayWebhookPanel — unconfigured', () => {
  it('explains the setup and offers Generate; no waiting/verified status', () => {
    authState.tenant = makeTenant();
    render(<BtcPayWebhookPanel />);

    expect(screen.getByText('Not configured')).toBeTruthy();
    expect(screen.getByText(/No webhook secret yet/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Generate webhook secret/ })).toBeTruthy();
    expect(screen.queryByText(/Waiting for first webhook/)).toBeNull();
    expect(screen.queryByText(/Webhook verified/)).toBeNull();
    expect(apiMock.post).not.toHaveBeenCalled();
  });
});

describe('BtcPayWebhookPanel — one-time reveal', () => {
  it('shows secret, URL, and both events as a 3-step checklist after generating', async () => {
    authState.tenant = makeTenant();
    mockGenerateResponse();
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));

    expect(await screen.findByText(SECRET)).toBeTruthy();
    expect(apiMock.post).toHaveBeenCalledWith('/tenants/me/btcpay/webhook-secret');
    expect(screen.getByText(WEBHOOK_URL)).toBeTruthy();
    expect(screen.getByText(/Shown only once — paste it into BTCPay now/)).toBeTruthy();
    expect(screen.getByText(/InvoiceSettled/)).toBeTruthy();
    expect(screen.getByText(/InvoicePaymentSettled/)).toBeTruthy();
    expect(screen.getByText(/Create the webhook in BTCPay/)).toBeTruthy();
  });

  it('hints that a local-only host is the address BTCPay must reach', async () => {
    authState.tenant = makeTenant();
    mockGenerateResponse();
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));

    await screen.findByText(SECRET);
    expect(screen.getByText(/the address BTCPay must reach/)).toBeTruthy();
  });

  it('shows no local hint for a public webhook URL', async () => {
    authState.tenant = makeTenant();
    apiMock.post.mockResolvedValueOnce({
      data: {
        secret: SECRET,
        webhook_url: 'https://opensplit.example.com/api/v1/webhooks/btcpay/tenant-1',
        events: ['InvoiceSettled', 'InvoicePaymentSettled'],
      },
    });
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));

    await screen.findByText(SECRET);
    expect(screen.queryByText(/the address BTCPay must reach/)).toBeNull();
  });

  it('copies the secret and the webhook URL', async () => {
    authState.tenant = makeTenant();
    mockGenerateResponse();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));
    await screen.findByText(SECRET);

    fireEvent.click(screen.getByRole('button', { name: 'Copy webhook secret' }));
    expect(writeText).toHaveBeenCalledWith(SECRET);
    fireEvent.click(screen.getByRole('button', { name: 'Copy webhook URL' }));
    expect(writeText).toHaveBeenCalledWith(WEBHOOK_URL);
  });

  it('never renders the secret again after the reveal is dismissed', async () => {
    authState.tenant = makeTenant();
    mockGenerateResponse();
    const { container } = render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));
    await screen.findByText(SECRET);

    fireEvent.click(screen.getByRole('button', { name: /Done — I saved it in BTCPay/ }));

    expect(screen.queryByText(SECRET)).toBeNull();
    expectTextAbsent(container, SECRET);
  });
});

describe('BtcPayWebhookPanel — verification states', () => {
  it('shows "Waiting for first webhook…" when a secret is set but unverified', () => {
    authState.tenant = makeTenant({ btcpay_webhook_secret_set: true, last_webhook_at: null });
    render(<BtcPayWebhookPanel />);

    expect(screen.getByText('Waiting')).toBeTruthy();
    expect(screen.getByText(/Waiting for first webhook/)).toBeTruthy();
    expect(screen.queryByText(/Webhook verified/)).toBeNull();
  });

  it('shows "Webhook verified — last event …" with a relative time when verified', () => {
    authState.tenant = makeTenant({
      btcpay_webhook_secret_set: true,
      last_webhook_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    });
    render(<BtcPayWebhookPanel />);

    expect(screen.getByText('Verified')).toBeTruthy();
    expect(screen.getByText(/Webhook verified — last event 5 minutes ago/)).toBeTruthy();
    expect(screen.queryByText(/Waiting for first webhook/)).toBeNull();
  });

  it('polls the tenant every ~10s while a secret is set', () => {
    vi.useFakeTimers();
    authState.tenant = makeTenant({ btcpay_webhook_secret_set: true, last_webhook_at: null });
    render(<BtcPayWebhookPanel />);

    expect(authState.refreshTenant).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10_000);
    expect(authState.refreshTenant).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(20_000);
    expect(authState.refreshTenant).toHaveBeenCalledTimes(3);
  });

  it('does not poll while no secret is configured', () => {
    vi.useFakeTimers();
    authState.tenant = makeTenant();
    render(<BtcPayWebhookPanel />);

    vi.advanceTimersByTime(30_000);
    expect(authState.refreshTenant).not.toHaveBeenCalled();
  });
});

describe('BtcPayWebhookPanel — regenerate', () => {
  it('asks for confirmation before regenerating', async () => {
    authState.tenant = makeTenant({ btcpay_webhook_secret_set: true, last_webhook_at: null });
    mockGenerateResponse();
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Regenerate secret/ }));
    expect(apiMock.post).not.toHaveBeenCalled();
    expect(screen.getByText('Regenerate webhook secret?')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

    expect(await screen.findByText(SECRET)).toBeTruthy();
    expect(apiMock.post).toHaveBeenCalledWith('/tenants/me/btcpay/webhook-secret');
  });

  it('warns that BTCPay needs the new secret until re-verified', async () => {
    authState.tenant = makeTenant({ btcpay_webhook_secret_set: true, last_webhook_at: null });
    mockGenerateResponse();
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Regenerate secret/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }));
    await screen.findByText(SECRET);

    expect(
      screen.getByText(/Update the secret in BTCPay — old events will be rejected/)
    ).toBeTruthy();
    // The warning survives dismissing the reveal (still unverified).
    fireEvent.click(screen.getByRole('button', { name: /Done — I saved it in BTCPay/ }));
    expect(
      screen.getByText(/Update the secret in BTCPay — old events will be rejected/)
    ).toBeTruthy();
  });

  it('shows no regenerate warning on a first-time generation', async () => {
    authState.tenant = makeTenant();
    mockGenerateResponse();
    render(<BtcPayWebhookPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Generate webhook secret/ }));
    await screen.findByText(SECRET);

    expect(screen.queryByText(/old events will be rejected/)).toBeNull();
  });
});
