import { describe, expect, it } from 'vitest';
import { getGreeting } from './greeting';

describe('getGreeting', () => {
  it('uses the morning greeting before noon', () => {
    expect(getGreeting(0)).toBe('Good morning');
    expect(getGreeting(11)).toBe('Good morning');
  });

  it('uses the afternoon greeting from noon through 18:59', () => {
    expect(getGreeting(12)).toBe('Good afternoon');
    expect(getGreeting(18)).toBe('Good afternoon');
  });

  it('uses the evening greeting from 19:00 onward', () => {
    expect(getGreeting(19)).toBe('Good evening');
    expect(getGreeting(23)).toBe('Good evening');
  });
});
