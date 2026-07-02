// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

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
        brand_display_name: null,
        brand_color: null,
        brand_logo_url: null,
        public_slug: 'coffee',
        public_transparency_enabled: false,
        active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
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
vi.mock('@/lib/api', () => ({ default: { patch: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SettingsPage } from './SettingsPage';

afterEach(cleanup);

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
