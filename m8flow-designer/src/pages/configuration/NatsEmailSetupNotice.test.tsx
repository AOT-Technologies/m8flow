import { render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mockFetchNatsEmailStatus = vi.fn();
vi.mock('@/lib/secretsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/secretsApi')>('@/lib/secretsApi');
  return { ...actual, fetchNatsEmailStatus: (...args: unknown[]) => mockFetchNatsEmailStatus(...args) };
});

import { NatsEmailSetupNotice, useNatsEmailStatus } from './NatsEmailSetupNotice';

const STATUS = {
  configured: false,
  requiredKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optionalKeys: [],
  missingKeys: ['NATS_SMTP_HOST'],
  unreadableKeys: ['NATS_SMTP_FROM_EMAIL'],
  configuredKeys: [],
  waitingCount: 0,
};

describe('useNatsEmailStatus', () => {
  afterEach(() => vi.clearAllMocks());

  it('does not call the API without access', () => {
    const { result } = renderHook(() => useNatsEmailStatus({ tenantId: null, enabled: false }));
    expect(result.current).toEqual({ status: null, failed: false });
    expect(mockFetchNatsEmailStatus).not.toHaveBeenCalled();
  });

  it('keeps the last status while reloading, so the reminder does not flicker', async () => {
    mockFetchNatsEmailStatus.mockResolvedValueOnce(STATUS).mockReturnValueOnce(new Promise(() => {}));
    const { result, rerender } = renderHook(
      ({ reloadKey }) => useNatsEmailStatus({ tenantId: 't1', enabled: true, reloadKey }),
      { initialProps: { reloadKey: 0 } },
    );
    await waitFor(() => expect(result.current.status).toEqual(STATUS));

    rerender({ reloadKey: 1 });

    expect(mockFetchNatsEmailStatus).toHaveBeenCalledTimes(2);
    expect(result.current.status).toEqual(STATUS);
  });

  it('starts over for a different tenant', async () => {
    mockFetchNatsEmailStatus.mockResolvedValueOnce(STATUS).mockReturnValueOnce(new Promise(() => {}));
    const { result, rerender } = renderHook(
      ({ tenantId }) => useNatsEmailStatus({ tenantId, enabled: true }),
      { initialProps: { tenantId: 't1' } },
    );
    await waitFor(() => expect(result.current.status).toEqual(STATUS));

    rerender({ tenantId: 't2' });

    expect(result.current.status).toBeNull();
    expect(mockFetchNatsEmailStatus).toHaveBeenLastCalledWith('t2');
  });

  it('reports a failed read', async () => {
    mockFetchNatsEmailStatus.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useNatsEmailStatus({ tenantId: null, enabled: true }));
    await waitFor(() => expect(result.current.failed).toBe(true));
  });
});

describe('NatsEmailSetupNotice', () => {
  it('names missing and unreadable variables separately', () => {
    render(<NatsEmailSetupNotice status={STATUS} />);
    expect(screen.getByText('Missing required variables:').parentElement).toHaveTextContent('NATS_SMTP_HOST');
    expect(screen.getByText(/These variables can't be read/).parentElement).toHaveTextContent('NATS_SMTP_FROM_EMAIL');
    expect(screen.queryByTestId('nats-email-waiting')).not.toBeInTheDocument();
  });

  it('warns with the count when emails are waiting', () => {
    render(<NatsEmailSetupNotice status={{ ...STATUS, waitingCount: 4 }} />);
    expect(screen.getByTestId('nats-email-waiting')).toHaveTextContent('4');
  });

  it('renders nothing once configured or before the status is known', () => {
    const { container, rerender } = render(<NatsEmailSetupNotice status={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<NatsEmailSetupNotice status={{ ...STATUS, configured: true }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
