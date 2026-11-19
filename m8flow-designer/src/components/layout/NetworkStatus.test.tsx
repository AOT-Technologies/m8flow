import { act, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OfflineBanner, RouteError } from './NetworkStatus';

function setOnline(online: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(online);
  act(() => {
    window.dispatchEvent(new Event(online ? 'online' : 'offline'));
  });
}

function renderFailingRoute(error: Error) {
  const Throws = () => {
    throw error;
  };
  const router = createMemoryRouter([{ path: '/', element: <Throws />, errorElement: <RouteError /> }]);
  render(<RouterProvider router={router} />);
}

describe('RouteError', () => {
  const reload = vi.fn();

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    reload.mockReset();
  });

  function stubReload() {
    vi.stubGlobal('location', { ...window.location, reload });
  }

  it('shows a connection message and Retry instead of the raw chunk error', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    stubReload();
    renderFailingRoute(new TypeError('Failed to fetch dynamically imported module: https://x/assets/Page-abc.js'));

    expect(screen.getByRole('alert')).toHaveTextContent('Unable to connect. Please check your internet connection.');
    expect(screen.queryByText(/dynamically imported module/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reloads by itself when the connection comes back', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    stubReload();
    renderFailingRoute(new TypeError('Failed to fetch dynamically imported module'));

    setOnline(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('shows a generic message for a non-network error', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderFailingRoute(new Error('Cannot read properties of undefined'));

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong while loading this page.');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('OfflineBanner', () => {
  afterEach(() => vi.restoreAllMocks());

  it('appears while offline and goes away once back online', () => {
    render(<OfflineBanner />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    setOnline(false);
    expect(screen.getByRole('alert')).toHaveTextContent("You're offline.");

    setOnline(true);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
