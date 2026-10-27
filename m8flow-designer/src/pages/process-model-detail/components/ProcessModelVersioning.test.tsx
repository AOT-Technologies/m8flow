import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { processModelStatusToPillProps } from '@/components/library/pill/processModelStatusToPillProps';
import type { ProcessModelDetail, ProcessModelVersion, ProcessModelVersionPage } from '@/lib/api';
import { ProcessModelHistoryDialog } from './ProcessModelHistoryDialog';
import { ProcessModelOverview } from './ProcessModelOverview';

const DETAIL: ProcessModelDetail = {
  id: 'finance/invoice-approval',
  tenant_id: 't1',
  display_name: 'Invoice Approval',
  description: '',
  group_id: 'finance',
  group_display_name: 'Finance',
  last_run_at: null,
  running_now: 0,
  runs_30d: 0,
  status: 'published',
  live_version: 2,
  has_unpublished_changes: true,
  recent_instances: [],
  files: [],
};

function version(n: number, overrides: Partial<ProcessModelVersion> = {}): ProcessModelVersion {
  return {
    version: n,
    action: 'save',
    created_by: 'editor',
    created_at: null,
    reverted_from_version: null,
    primary_file_name: 'invoice-approval.bpmn',
    is_live: false,
    ...overrides,
  };
}

function page(results: ProcessModelVersion[], current: number, pages: number): ProcessModelVersionPage {
  return { results, pagination: { page: current, per_page: results.length, total: results.length, pages } };
}

describe('processModelStatusToPillProps', () => {
  it('labels a published model with pending edits', () => {
    expect(processModelStatusToPillProps('published', true).children).toBe('Published – Unpublished changes');
    expect(processModelStatusToPillProps('published', false).children).toBe('Published');
    // Only a published model can have unpublished changes.
    expect(processModelStatusToPillProps('draft', true).children).toBe('Draft');
  });
});

describe('ProcessModelOverview versioned publishing', () => {
  it('puts Publish changes in Start’s place and keeps the live start in the menu', async () => {
    const onChangeStatus = vi.fn().mockResolvedValue(undefined);
    const onStart = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onChangeStatus={onChangeStatus} onStart={onStart} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Published – Unpublished changes')).toBeInTheDocument();
    expect(screen.getByTestId('process-model-live-version')).toHaveTextContent('v2');
    expect(screen.queryByRole('button', { name: /start process/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /publish changes/i }));
    expect(onChangeStatus).toHaveBeenCalledWith('published');

    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /start live version/i }));
    await waitFor(() => expect(onStart).toHaveBeenCalledTimes(1));
  });

  it('shows Start in the primary slot once the edits are published', () => {
    render(
      <MemoryRouter>
        <ProcessModelOverview
          detail={{ ...DETAIL, has_unpublished_changes: false }}
          onChangeStatus={vi.fn()}
          onStart={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: /start process/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /publish changes/i })).not.toBeInTheDocument();
  });

  it('keeps Start for a user who can start but not publish', () => {
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onStart={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: /start process/i })).toBeInTheDocument();
  });

  it('hides Publish changes and History without the permissions', () => {
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button', { name: /publish changes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /history/i })).not.toBeInTheDocument();
  });

  it('has no Publish changes when the working copy matches the live version', () => {
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={{ ...DETAIL, has_unpublished_changes: false }} onChangeStatus={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button', { name: /publish changes/i })).not.toBeInTheDocument();
  });

  it('opens History from the header', async () => {
    const onFetchVersions = vi.fn().mockResolvedValue(page([version(2, { action: 'publish', is_live: true })], 1, 1));
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onFetchVersions={onFetchVersions} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole('button', { name: /history/i }));
    expect(await screen.findByTestId('process-model-version-2')).toHaveTextContent('Published');
    expect(onFetchVersions).toHaveBeenCalledWith(1);
  });
});

describe('ProcessModelHistoryDialog', () => {
  it('scrolls inside the modal and loads more pages', async () => {
    const first = Array.from({ length: 50 }, (_, i) => version(60 - i));
    const onFetchPage = vi
      .fn()
      .mockResolvedValueOnce(page(first, 1, 2))
      .mockResolvedValueOnce(page([version(10), version(9)], 2, 2));

    render(<ProcessModelHistoryDialog open onOpenChange={vi.fn()} onFetchPage={onFetchPage} />);

    const list = await screen.findByTestId('process-model-history-list');
    expect(list.className).toContain('overflow-y-auto');
    expect(list.className).toContain('max-h-[60vh]');
    expect(await screen.findByTestId('process-model-version-60')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /load more/i }));
    expect(await screen.findByTestId('process-model-version-9')).toBeInTheDocument();
    expect(onFetchPage).toHaveBeenLastCalledWith(2);
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });

  it('shows no Revert without the revert permission', async () => {
    render(
      <ProcessModelHistoryDialog
        open
        onOpenChange={vi.fn()}
        onFetchPage={vi.fn().mockResolvedValue(page([version(2), version(1)], 1, 1))}
      />,
    );
    await screen.findByTestId('process-model-version-1');
    expect(screen.queryByRole('button', { name: /^revert$/i })).not.toBeInTheDocument();
  });

  it('confirms before reverting, then closes the history', async () => {
    const onFetchPage = vi
      .fn()
      .mockResolvedValue(page([version(2, { action: 'publish', is_live: true }), version(1)], 1, 1));
    const onRevert = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();
    render(<ProcessModelHistoryDialog open onOpenChange={onOpenChange} onFetchPage={onFetchPage} onRevert={onRevert} />);

    // The latest version is already the working copy: no Revert on it.
    const latest = await screen.findByTestId('process-model-version-2');
    expect(within(latest).queryByRole('button', { name: /revert/i })).not.toBeInTheDocument();

    const row = screen.getByTestId('process-model-version-1');
    await userEvent.click(within(row).getByRole('button', { name: /revert/i }));
    expect(onRevert).not.toHaveBeenCalled();

    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /^revert$/i }));

    await waitFor(() => expect(onRevert).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
