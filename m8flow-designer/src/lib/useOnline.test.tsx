import { renderHook } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useOnline } from './useOnline';

afterEach(() => vi.unstubAllGlobals());

describe('useOnline', () => {
  it('renders on the server without browser globals', () => {
    function Status() { return <span>{String(useOnline())}</span>; }
    vi.stubGlobal('navigator', undefined);
    vi.stubGlobal('window', undefined);
    expect(renderToString(<Status />)).toBe('<span>true</span>');
  });

  it('has a safe client snapshot without navigator', () => {
    vi.stubGlobal('navigator', undefined);
    const { result } = renderHook(() => useOnline());
    expect(result.current).toBe(true);
  });
});
