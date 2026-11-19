import { act, fireEvent, render, screen } from '@testing-library/react';
import { StrictMode, useState } from 'react';
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
  return render(<StrictMode><RouterProvider router={router} /></StrictMode>);
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
    setOnline(false);
    renderFailingRoute(new TypeError('Failed to fetch dynamically imported module'));
    expect(reload).not.toHaveBeenCalled();
    setOnline(true);
    expect(reload).toHaveBeenCalledTimes(1);
    setOnline(true);
    setOnline(false);
    setOnline(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does not reload for an online event without an offline transition, including after remount', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    stubReload();
    setOnline(true);
    const first = renderFailingRoute(new TypeError('Load failed'));
    setOnline(true);
    first.unmount();
    renderFailingRoute(new TypeError('Load failed'));
    setOnline(true);
    expect(reload).not.toHaveBeenCalled();
  });

  it('cleans up on unmount', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    stubReload();
    setOnline(false);
    const view = renderFailingRoute(new TypeError('Failed to fetch'));
    view.unmount();
    setOnline(true);
    expect(reload).not.toHaveBeenCalled();
  });

  it('shows a generic message for a non-network error', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    stubReload();
    setOnline(false);
    renderFailingRoute(new Error('Cannot read properties of undefined'));

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong while loading this page.');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    setOnline(true);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('OfflineBanner', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows on an initially offline render and preserves sibling input through reconnection', () => {
    setOnline(false);
    function Editor() {
      const [text, setText] = useState('');
      return <><OfflineBanner /><input aria-label="Draft" value={text} onChange={(e) => setText(e.target.value)} /></>;
    }
    render(<StrictMode><Editor /></StrictMode>);
    expect(screen.getByRole('alert')).toHaveTextContent("You're offline.");
    fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Unsaved work' } });
    setOnline(true);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Draft')).toHaveValue('Unsaved work');
  });

  it('appears while offline and goes away once back online', () => {
    render(<OfflineBanner />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    setOnline(false);
    expect(screen.getByRole('alert')).toHaveTextContent("You're offline.");

    setOnline(true);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
