import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ProcessModelHistoryDialog } from './ProcessModelHistoryDialog';

const VERSIONS = [
  { version: 2, published_by: 'editor', created_at: null, primary_file_name: 'a.bpmn', is_live: true },
  { version: 1, published_by: null, created_at: null, primary_file_name: 'a.bpmn', is_live: false },
];

function stubFetch(versions: unknown = VERSIONS) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = String(input).includes('/revert') && init?.method === 'POST'
      ? { id: 'finance/a', status: 'published', has_unpublished_changes: true }
      : versions;
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderDialog(props: Partial<Parameters<typeof ProcessModelHistoryDialog>[0]> = {}) {
  const onReverted = vi.fn();
  const onClose = vi.fn();
  render(
    <ProcessModelHistoryDialog
      open
      onClose={onClose}
      modifiedId="finance:a"
      tenantId="t1"
      writeTenantId="t1"
      canRevert
      onReverted={onReverted}
      {...props}
    />,
  );
  return { onReverted, onClose };
}

describe('ProcessModelHistoryDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists versions newest first with the live one marked', async () => {
    stubFetch();
    renderDialog();

    expect(await screen.findByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByText(/Published by editor/)).toBeInTheDocument();
    expect(screen.getByText(/Published before version history/)).toBeInTheDocument();
  });

  it('offers no Revert on the newest version', async () => {
    stubFetch();
    renderDialog();

    const rows = within(await screen.findByTestId('process-model-versions')).getAllByRole('listitem');
    expect(within(rows[0]).queryByRole('button', { name: /Revert/ })).not.toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', { name: /^Revert$/ })).toBeInTheDocument();
  });

  it('hides the history while confirming and returns to it on cancel', async () => {
    stubFetch();
    renderDialog();

    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));
    expect(await screen.findByText('Revert to version 1?')).toBeInTheDocument();
    expect(screen.queryByText('Version history')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(await screen.findByText('Version history')).toBeInTheDocument();
    expect(screen.queryByText('Revert to version 1?')).not.toBeInTheDocument();
  });

  it('shows a spinner while the revert runs', async () => {
    const fetchMock = stubFetch();
    const base = fetchMock.getMockImplementation()!;
    let finish: () => void = () => {};
    fetchMock.mockImplementation((input, init) =>
      String(input).includes('/revert')
        ? new Promise((resolve) => {
            finish = () => resolve(base(input, init));
          })
        : base(input, init),
    );
    renderDialog();

    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));
    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));

    const pending = await screen.findByRole('button', { name: /Reverting/ });
    expect(pending).toBeDisabled();
    expect(within(pending).getByRole('status')).toBeInTheDocument();
    finish();
  });

  it('reverts a version after confirmation', async () => {
    const fetchMock = stubFetch();
    const { onReverted, onClose } = renderDialog();

    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));
    expect(await screen.findByText('Revert to version 1?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Revert$/ }));

    await waitFor(() => expect(onReverted).toHaveBeenCalledWith(expect.objectContaining({ has_unpublished_changes: true }), 1));
    expect(onClose).toHaveBeenCalled();
    const revert = fetchMock.mock.calls.find(([url]) => String(url).includes('/versions/1/revert'));
    expect(String(revert?.[0])).toContain('tenantId=t1');
  });

  it('hides Revert without the revert permission', async () => {
    stubFetch();
    renderDialog({ canRevert: false });

    expect(await screen.findByText('Version 2')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Revert/ })).not.toBeInTheDocument();
  });

  it('blocks Revert while there are unsaved edits', async () => {
    stubFetch();
    renderDialog({ revertBlockedReason: 'Save or discard your changes before reverting.' });

    expect(await screen.findByRole('button', { name: /^Revert$/ })).toBeDisabled();
  });

  it('explains an empty history', async () => {
    stubFetch([]);
    renderDialog();

    expect(await screen.findByText(/Not published yet/)).toBeInTheDocument();
  });

  it('stays busy until the page has reloaded after the revert', async () => {
    stubFetch();
    let reloaded: () => void = () => {};
    const onReverted = vi.fn(() => new Promise<void>((resolve) => { reloaded = resolve; }));
    const onClose = vi.fn();
    renderDialog({ onReverted, onClose });

    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));
    fireEvent.click(await screen.findByRole('button', { name: /^Revert$/ }));

    await waitFor(() => expect(onReverted).toHaveBeenCalledWith(expect.anything(), 1));
    expect(screen.getByRole('button', { name: /Reverting/ })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();

    reloaded();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
