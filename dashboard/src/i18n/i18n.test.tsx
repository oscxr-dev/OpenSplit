// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';

// Node's experimental `localStorage` global shadows jsdom's with `undefined`
// unless --localstorage-file is set. Install a Map-backed shim BEFORE the
// i18n module initializes so the language detector can cache the choice,
// exactly like it does in a real browser.
vi.hoisted(() => {
  const backing = new Map<string, string>();
  const shim: Storage = {
    getItem: (key) => (backing.has(key) ? backing.get(key)! : null),
    setItem: (key, value) => void backing.set(key, String(value)),
    removeItem: (key) => void backing.delete(key),
    clear: () => backing.clear(),
    key: (index) => [...backing.keys()][index] ?? null,
    get length() {
      return backing.size;
    },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: shim, configurable: true });
});

import i18n, { LANGUAGE_STORAGE_KEY } from '@/i18n';
import en from '@/i18n/locales/en.json';
import es from '@/i18n/locales/es.json';
import { ErrorState } from '@/components/shared/ErrorState';

/** Flatten a nested catalog into dot-paths ("settings.btcpay.title"). Plural
 *  variants (_one/_other) appear as distinct paths, so parity covers them. */
function flattenKeys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key)
  );
}

function flattenValues(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (typeof value !== 'object' || value === null) return [];
  return Object.values(value as Record<string, unknown>).flatMap(flattenValues);
}

describe('locale catalogs (en/es parity)', () => {
  it('en and es expose identical key sets — fails on drift', () => {
    expect(flattenKeys(es).sort()).toEqual(flattenKeys(en).sort());
  });

  it('has no empty translations in either catalog', () => {
    expect(flattenValues(en).every((text) => text.trim().length > 0)).toBe(true);
    expect(flattenValues(es).every((text) => text.trim().length > 0)).toBe(true);
  });

  it('keeps interpolation placeholders consistent between en and es', () => {
    const byKey = (catalog: unknown) => {
      const map = new Map<string, Set<string>>();
      for (const key of flattenKeys(catalog)) {
        const text = key.split('.').reduce<unknown>(
          (node, part) => (node as Record<string, unknown>)[part],
          catalog
        ) as string;
        map.set(key, new Set(text.match(/\{\{\s*\w+\s*\}\}/g) ?? []));
      }
      return map;
    };
    const enPlaceholders = byKey(en);
    const esPlaceholders = byKey(es);
    for (const [key, expected] of enPlaceholders) {
      expect([...(esPlaceholders.get(key) ?? [])].sort(), `placeholders differ for ${key}`).toEqual(
        [...expected].sort()
      );
    }
  });
});

describe('language switching', () => {
  afterEach(async () => {
    cleanup();
    await act(async () => {
      await i18n.changeLanguage('en');
    });
    window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
  });

  it('re-renders mounted components in Spanish when the language changes to es', async () => {
    render(<ErrorState onRetry={() => {}} />);

    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();

    await act(async () => {
      await i18n.changeLanguage('es');
    });

    expect(screen.getByText('Algo salió mal')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeTruthy();
    expect(screen.queryByText('Something went wrong')).toBeNull();
  });

  it('persists the chosen language to localStorage for the next visit', async () => {
    await act(async () => {
      await i18n.changeLanguage('es');
    });
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('es');

    await act(async () => {
      await i18n.changeLanguage('en');
    });
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en');
  });
});
