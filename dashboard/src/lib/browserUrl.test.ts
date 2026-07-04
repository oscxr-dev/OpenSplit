import { describe, expect, it } from 'vitest';
import { isDockerHostUrl, isValidServerUrl, toBrowserUrl } from './browserUrl';

describe('toBrowserUrl', () => {
  it('rewrites host.docker.internal to the browser hostname', () => {
    expect(toBrowserUrl('http://host.docker.internal:3003', 'localhost')).toBe(
      'http://localhost:3003/'
    );
  });

  it('preserves port, path, query, and hash through the rewrite', () => {
    const rewritten = toBrowserUrl(
      'http://host.docker.internal:3003/api-keys/authorize?applicationName=OpenSplit&permissions=btcpay.store.canviewinvoices#top',
      '192.168.1.20'
    );
    expect(rewritten).toBe(
      'http://192.168.1.20:3003/api-keys/authorize?applicationName=OpenSplit&permissions=btcpay.store.canviewinvoices#top'
    );
  });

  it('leaves normal hostnames untouched (exact string, no re-serialization)', () => {
    const untouched = 'https://btcpay.example.com/api-keys/authorize?x=1';
    expect(toBrowserUrl(untouched, 'localhost')).toBe(untouched);
    expect(toBrowserUrl('http://localhost:3003/path', 'localhost')).toBe(
      'http://localhost:3003/path'
    );
  });

  it('passes through values that are not URLs and empty browser hostnames', () => {
    expect(toBrowserUrl('not a url', 'localhost')).toBe('not a url');
    expect(toBrowserUrl('http://host.docker.internal:3003', '')).toBe(
      'http://host.docker.internal:3003'
    );
  });
});

describe('isDockerHostUrl', () => {
  it('detects host.docker.internal URLs only', () => {
    expect(isDockerHostUrl('http://host.docker.internal:3003')).toBe(true);
    expect(isDockerHostUrl('https://btcpay.example.com')).toBe(false);
    expect(isDockerHostUrl('not a url')).toBe(false);
  });
});

describe('isValidServerUrl', () => {
  it('accepts real hosts, localhost, host.docker.internal, and IPs', () => {
    expect(isValidServerUrl('https://btcpay.example.com')).toBe(true);
    expect(isValidServerUrl('http://localhost:3003')).toBe(true);
    expect(isValidServerUrl('http://host.docker.internal:3003')).toBe(true);
    expect(isValidServerUrl('http://192.168.1.20:3003')).toBe(true);
  });

  it('rejects single-label hosts like "http://h"', () => {
    expect(isValidServerUrl('http://h')).toBe(false);
    expect(isValidServerUrl('http://h:3003')).toBe(false);
    expect(isValidServerUrl('https://internal')).toBe(false);
  });

  it('rejects schemeless input and non-http schemes', () => {
    expect(isValidServerUrl('btcpay.example.com')).toBe(false);
    expect(isValidServerUrl('ftp://btcpay.example.com')).toBe(false);
    expect(isValidServerUrl('')).toBe(false);
  });
});
