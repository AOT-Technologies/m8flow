import { describe, expect, it } from 'vitest';

import { resolveConfiguredApiVersion } from './apiVersion';

describe('resolveConfiguredApiVersion', () => {
  it.each([undefined, '', '  '])('defaults %s to V1', (value) => {
    expect(resolveConfiguredApiVersion(value)).toBe('1.0');
  });

  it.each(['1.0', '2.0', ' 2.0 '])('accepts supported version %s', (value) => {
    expect(resolveConfiguredApiVersion(value)).toBe(value.trim());
  });

  it.each(['v2', '3.0'])('fails clearly for unsupported version %s', (value) => {
    expect(() => resolveConfiguredApiVersion(value)).toThrow(
      'Unsupported VITE_API_VERSION',
    );
  });
});
