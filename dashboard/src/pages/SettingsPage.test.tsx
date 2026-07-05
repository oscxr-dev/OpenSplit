// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

// jsdom does not implement <dialog> methods used by ConfirmDialog.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
  };
});

const TENANT_ID = '4f0c2f9e-9d3a-4b7c-8e21-6a5f0d1c2b3a';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    logout: vi.fn(),
    refreshTenant: vi.fn(),
    tenant: {
      tenant: {
        id: TENANT_ID,
        name: 'Coffee Co',
        adapter_type: 'btcpay',
        lnbits_url: null,
        // Stale branding must never surface: display paths use tenant.name only.
        brand_display_name: 'BitCrew',
        brand_color: null,
        brand_logo_url: null,
        public_slug: 'coffee',
        public_transparency_enabled: false,
        btcpay_url: 'https://btcpay.local',
        btcpay_store_id: 'store-1',
        btcpay_api_key_set: true,
        btcpay_api_key_last4: '9F3A',
        active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
      connection_status: 'ok',
      lnbits_status: 'ok',
    },
  }),
}));
vi.mock('@/hooks/useSplits', () => ({
  useSplits: () => ({ data: [], isLoading: false }),
  useToggleSplitPublic: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/useTheme', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn() }),
}));
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() }),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('@/lib/api', () => ({ default: { patch: vi.fn(), get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// The relocated pipeline-health strip pulls in react-router's Link and the
// tenant-status query; it has its own tests, so stub it here to keep these
// SettingsPage tests focused on the tabs/settings behavior.
vi.mock('@/components/team/StatusStrip', () => ({ StatusStrip: () => null }));

import { SettingsPage } from './SettingsPage';

afterEach(() => {
  cleanup();
  // Reset the deep-link hash so each test starts on the default tab.
  window.history.replaceState(null, '', '/');
});

describe('SettingsPage tabs', () => {
  it('renders the four tabs and opens Connection by default', () => {
    render(<SettingsPage />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'Connection',
      'Store',
      'Public page',
      'Appearance',
    ]);
    expect(screen.getByRole('tab', { name: 'Connection' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('BTCPay connection')).toBeTruthy();
    expect(screen.queryByText('Store name')).toBeNull();
  });

  it('switches sections when a tab is clicked', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: 'Store' }));
    expect(screen.getByText('Store name')).toBeTruthy();
    expect(screen.getByText('Public URL')).toBeTruthy();
    expect(screen.getByText('Public location')).toBeTruthy();
    expect(screen.queryByText('BTCPay connection')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: 'Public page' }));
    expect(screen.getByText('Public proof')).toBeTruthy();

    fireEvent.click(screen.getByRole('tab', { name: 'Appearance' }));
    expect(screen.getByRole('button', { name: /Dark/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Light/ })).toBeTruthy();
  });

  it('deep-links a tab from the URL hash (/settings#public-page)', () => {
    window.location.hash = '#public-page';
    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: 'Public page' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Public proof')).toBeTruthy();
    expect(screen.queryByText('BTCPay connection')).toBeNull();
  });

  it('writes the selected tab into the hash for deep-linking', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: 'Store' }));
    expect(window.location.hash).toBe('#store');
  });

  it('moves selection with arrow keys (tablist keyboard support)', () => {
    render(<SettingsPage />);

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Connection' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Store' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Store name')).toBeTruthy();

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Store' }), { key: 'ArrowLeft' });
    expect(screen.getByRole('tab', { name: 'Connection' }).getAttribute('aria-selected')).toBe('true');
  });
});

describe('SettingsPage stale branding (P-F)', () => {
  it('never renders brand_display_name ("BitCrew") on any tab', () => {
    render(<SettingsPage />);

    for (const tabName of ['Connection', 'Store', 'Public page', 'Appearance']) {
      fireEvent.click(screen.getByRole('tab', { name: tabName }));
      expect(screen.queryByText(/BitCrew/)).toBeNull();
    }
  });

  it('shows the editable tenant name as the store name value', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: 'Store' }));
    expect((screen.getByLabelText('Store or team name') as HTMLInputElement).value).toBe('Coffee Co');
  });
});

describe('SettingsPage tenant UUID privacy', () => {
  it('keeps the tenant UUID collapsed under Advanced by default', () => {
    render(<SettingsPage />);

    // The UUID only lives inside a <details> element that starts collapsed.
    const uuidNode = screen.getByText((content) => content.includes(TENANT_ID));
    const details = uuidNode.closest('details');
    expect(details).not.toBeNull();
    expect(details!.open).toBe(false);
    expect(screen.getByText('Advanced')).toBeTruthy();
  });

  it('never renders the UUID outside the collapsed Advanced section', () => {
    const { container } = render(<SettingsPage />);

    // Walk actual text nodes so ancestor wrappers don't false-positive.
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const leaks: string[] = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.textContent?.includes(TENANT_ID) && !node.parentElement?.closest('details')) {
        leaks.push(node.textContent);
      }
    }
    expect(leaks).toEqual([]);
  });
});
