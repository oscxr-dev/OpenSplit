// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { TenantHealth } from '@/types/api';

const authState = vi.hoisted(() => ({
  tenant: null as TenantHealth | null,
}));

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ tenant: authState.tenant, refreshTenant: vi.fn() }),
}));
vi.mock('@/lib/api', () => ({ default: apiMock }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { BtcPayConnectionPanel } from './BtcPayConnectionPanel';

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
      btcpay_url: null,
      btcpay_store_id: null,
      btcpay_api_key_set: false,
      btcpay_api_key_last4: null,
      active: true,
      created_at: '2026-01-01T00:00:00Z',
      ...overrides,
    },
    connection_status: 'ok',
    lnbits_status: 'ok',
  };
}

const CONFIGURED = {
  btcpay_url: 'https://btcpay.local',
  btcpay_store_id: 'store-1',
  btcpay_api_key_set: true,
  btcpay_api_key_last4: '9F3A',
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('BtcPayConnectionPanel — states', () => {
  it('renders a setup CTA (not an error) and disables Test when unconfigured', () => {
    authState.tenant = makeTenant();
    render(<BtcPayConnectionPanel />);

    expect(screen.getByText(/Not connected yet/)).toBeTruthy();
    const testButton = screen.getByRole('button', { name: /Test connection/ });
    expect((testButton as HTMLButtonElement).disabled).toBe(true);
    const authorizeButton = screen.getByRole('button', { name: /Open BTCPay/ });
    expect((authorizeButton as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/unlocks once the server URL is saved/)).toBeTruthy();
  });

  it('enables Test and the authorize link when fully configured', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    expect(screen.queryByText(/Not connected yet/)).toBeNull();
    expect((screen.getByRole('button', { name: /Test connection/ }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: /Open BTCPay/ }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('BtcPayConnectionPanel — API key never echoes', () => {
  it('renders an empty password input with a masked last4 placeholder when a key is stored', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    const keyInput = screen.getByLabelText('API key') as HTMLInputElement;
    expect(keyInput.type).toBe('password');
    expect(keyInput.value).toBe(''); // NEVER prefilled from the server
    expect(keyInput.placeholder).toContain('••••');
    expect(keyInput.placeholder).toContain('9F3A');
    expect(
      screen.getByText(/stored value is never shown\. Enter a new key to replace it/)
    ).toBeTruthy();
  });

  it('never renders any 4-char key suffix outside the placeholder', () => {
    authState.tenant = makeTenant(CONFIGURED);
    const { container } = render(<BtcPayConnectionPanel />);

    // The last4 may appear as an input placeholder but never as text content.
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      expect(walker.currentNode.textContent).not.toContain('9F3A');
    }
  });
});

describe('BtcPayConnectionPanel — test connection checklist', () => {
  it('renders three passed checks on success', async () => {
    authState.tenant = makeTenant(CONFIGURED);
    apiMock.post.mockResolvedValueOnce({
      data: {
        url_reachable: true,
        auth_ok: true,
        store_found: true,
        ok: true,
        detail: 'Connected. Server, API key, and store all check out.',
      },
    });
    render(<BtcPayConnectionPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Test connection/ }));

    expect(await screen.findByLabelText('Server reachable: passed')).toBeTruthy();
    expect(screen.getByLabelText('API key valid: passed')).toBeTruthy();
    expect(screen.getByLabelText('Store found: passed')).toBeTruthy();
    expect(apiMock.post).toHaveBeenCalledWith('/tenants/me/btcpay/test');
  });

  it('renders a rejected key distinctly, with later checks marked not checked', async () => {
    authState.tenant = makeTenant(CONFIGURED);
    apiMock.post.mockResolvedValueOnce({
      data: {
        url_reachable: true,
        auth_ok: false,
        store_found: null,
        ok: false,
        detail: 'BTCPay rejected the API key. Check the key and that it has access to this store ID.',
      },
    });
    render(<BtcPayConnectionPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Test connection/ }));

    expect(await screen.findByLabelText('Server reachable: passed')).toBeTruthy();
    expect(screen.getByLabelText('API key valid: failed')).toBeTruthy();
    expect(screen.getByLabelText('Store found: not checked')).toBeTruthy();
    expect(screen.getByText(/BTCPay rejected the API key/)).toBeTruthy();
  });

  it('renders an unreachable server with auth and store not checked', async () => {
    authState.tenant = makeTenant(CONFIGURED);
    apiMock.post.mockResolvedValueOnce({
      data: {
        url_reachable: false,
        auth_ok: null,
        store_found: null,
        ok: false,
        detail: 'Could not reach the BTCPay server. Check the URL and that the server is running.',
      },
    });
    render(<BtcPayConnectionPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Test connection/ }));

    expect(await screen.findByLabelText('Server reachable: failed')).toBeTruthy();
    expect(screen.getByLabelText('API key valid: not checked')).toBeTruthy();
    expect(screen.getByLabelText('Store found: not checked')).toBeTruthy();
  });
});

describe('BtcPayConnectionPanel — saving', () => {
  it('PATCHes only meaningful diffs and clears the key input after saving', async () => {
    authState.tenant = makeTenant(CONFIGURED);
    apiMock.patch.mockResolvedValueOnce({ data: {} });
    render(<BtcPayConnectionPanel />);

    const keyInput = screen.getByLabelText('API key') as HTMLInputElement;
    fireEvent.change(keyInput, { target: { value: '  new-key-value  ' } });
    fireEvent.click(screen.getByRole('button', { name: /Save connection/ }));

    expect(apiMock.patch).toHaveBeenCalledWith('/tenants/me', {
      btcpay_api_key: 'new-key-value',
    });
    expect((await screen.findByLabelText('API key') as HTMLInputElement).value).toBe('');
  });

  it('keeps Save disabled while nothing changed', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    const saveButton = screen.getByRole('button', { name: /Save connection/ });
    expect((saveButton as HTMLButtonElement).disabled).toBe(true);
  });

  it('rejects a single-label URL like "http://h" (Save disabled, inline error)', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    fireEvent.change(screen.getByLabelText('BTCPay server URL'), {
      target: { value: 'http://h' },
    });

    expect(screen.getByText(/Enter a full URL/)).toBeTruthy();
    expect(
      (screen.getByRole('button', { name: /Save connection/ }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(apiMock.patch).not.toHaveBeenCalled();
  });
});

describe('BtcPayConnectionPanel — labels', () => {
  it('renders a visible label for each connection input', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    expect(screen.getByLabelText('BTCPay server URL')).toBeTruthy();
    expect(screen.getByLabelText('Store ID')).toBeTruthy();
    expect(screen.getByLabelText('API key')).toBeTruthy();
  });
});

describe('BtcPayConnectionPanel — dirty-state hygiene', () => {
  it('disables Test connection while any field is dirty, with a save-first reason', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    const testButton = screen.getByRole('button', { name: /Test connection/ }) as HTMLButtonElement;
    expect(testButton.disabled).toBe(false);

    fireEvent.change(screen.getByLabelText('Store ID'), { target: { value: 'other-store' } });

    expect(testButton.disabled).toBe(true);
    expect(testButton.title).toBe('Save your changes first');
    expect(screen.getByText(/Unsaved changes/)).toBeTruthy();
  });

  it('marks a previous checklist as stale once fields are edited', async () => {
    authState.tenant = makeTenant(CONFIGURED);
    apiMock.post.mockResolvedValueOnce({
      data: { url_reachable: true, auth_ok: true, store_found: true, ok: true, detail: 'ok' },
    });
    render(<BtcPayConnectionPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Test connection/ }));
    await screen.findByLabelText('Server reachable: passed');
    expect(screen.queryByText(/Stale — settings changed/)).toBeNull();

    fireEvent.change(screen.getByLabelText('BTCPay server URL'), {
      target: { value: 'https://elsewhere.example.com' },
    });

    expect(screen.getByText(/Stale — settings changed/)).toBeTruthy();
  });

  it('Discard restores the stored values and clears the key input', () => {
    authState.tenant = makeTenant(CONFIGURED);
    render(<BtcPayConnectionPanel />);

    fireEvent.change(screen.getByLabelText('BTCPay server URL'), {
      target: { value: 'https://elsewhere.example.com' },
    });
    fireEvent.change(screen.getByLabelText('Store ID'), { target: { value: 'other-store' } });
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'candidate-key' } });

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));

    expect((screen.getByLabelText('BTCPay server URL') as HTMLInputElement).value).toBe(
      'https://btcpay.local'
    );
    expect((screen.getByLabelText('Store ID') as HTMLInputElement).value).toBe('store-1');
    expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
    expect(screen.queryByText(/Unsaved changes/)).toBeNull();
    expect(
      (screen.getByRole('button', { name: /Test connection/ }) as HTMLButtonElement).disabled
    ).toBe(false);
  });
});

describe('BtcPayConnectionPanel — browser-reachable authorize link (P-A)', () => {
  it('rewrites host.docker.internal to the browser hostname before opening', async () => {
    authState.tenant = makeTenant({
      ...CONFIGURED,
      btcpay_url: 'http://host.docker.internal:3003',
    });
    apiMock.get.mockResolvedValueOnce({
      data: {
        authorize_url:
          'http://host.docker.internal:3003/api-keys/authorize?applicationName=OpenSplit',
        permissions: [],
      },
    });
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<BtcPayConnectionPanel />);

    fireEvent.click(screen.getByRole('button', { name: /Open BTCPay/ }));

    // jsdom serves the test page from localhost, so that is the rewrite target.
    await vi.waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith(
        'http://localhost:3003/api-keys/authorize?applicationName=OpenSplit',
        '_blank',
        'noopener,noreferrer'
      )
    );
    expect(
      screen.getByText(/Server-side address; links open via localhost in your browser/)
    ).toBeTruthy();
    openSpy.mockRestore();
  });
});
