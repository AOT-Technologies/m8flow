import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, changeWorkingProcessVersion, fetchProcessModelVersions } from '@/lib/api';
import { ProcessModelVersionHistory } from './ProcessModelVersionHistory';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/api')>(),
  fetchProcessModelVersions: vi.fn(),
  changeWorkingProcessVersion: vi.fn(),
}));

const history = {
  status: 'published' as const,
  published_version: 30,
  draft_version: 31,
  has_unpublished_changes: true,
  working_revision: 'revision-1',
  versions: Array.from({ length: 30 }, (_, index) => ({
    version: 30 - index, published_at: null, published_by: null,
  })),
};

describe('Process model version history', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProcessModelVersions).mockResolvedValue(history);
  });

  it('offers read-only history and a keyboard-focusable list for long histories', async () => {
    render(<ProcessModelVersionHistory modifiedId="finance:invoice" canRestore={false} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Version History' }));
    const list = await screen.findByRole('region', { name: 'Process versions' });
    expect(list).toHaveAttribute('tabindex', '0');
    expect(list).toHaveClass('overflow-y-auto');
    expect(within(list).getByText('V1 Published')).toBeInTheDocument();
    expect(within(list).getByText('Live')).toBeInTheDocument();
    expect(within(list).queryByRole('button')).toBeNull();
    expect(screen.getAllByRole('button', { name: 'Close' }).length).toBeGreaterThan(0);
  });

  it('confirms draft replacement and announces the restored and live versions', async () => {
    const onChanged = vi.fn();
    const restored = {
      id: 'finance/invoice', display_name: 'Invoice', description: '', group_id: 'finance',
      group_display_name: 'Finance', status: 'published' as const, published_version: 30,
      draft_version: 31, working_revision: 'revision-2',
    };
    vi.mocked(changeWorkingProcessVersion).mockResolvedValue(restored);
    render(<ProcessModelVersionHistory modifiedId="finance:invoice" canRestore unsaved
      revision="revision-1" onChanged={onChanged} />);
    const trigger = screen.getByRole('button', { name: 'Version History' });
    fireEvent.click(trigger);
    const restoreButtons = await screen.findAllByRole('button', { name: 'Restore to Draft' });
    fireEvent.click(restoreButtons[restoreButtons.length - 1]);
    const confirmation = screen.getByRole('alertdialog');
    expect(confirmation).toHaveTextContent('Restore V1 to draft?');
    expect(confirmation).toHaveTextContent('This replaces the current draft.');
    expect(confirmation).toHaveTextContent('This also replaces unsaved edits');
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Restore to Draft' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(
      restored, 'V1 restored to V31 Draft. Start Process still runs V30. Publish Changes to make V31 live.',
    ));
    expect(trigger).toHaveFocus();
    expect(changeWorkingProcessVersion).toHaveBeenCalledWith(
      'finance:invoice', { operation: 'restore', version: 1 }, 'revision-1', undefined,
    );
  });

  it('keeps the confirmation open and preserves the editor when the draft is stale', async () => {
    const onChanged = vi.fn();
    vi.mocked(changeWorkingProcessVersion).mockRejectedValue(
      new ApiError('/working-version', 409, 'PUT', undefined, 'stale_working_revision'),
    );
    render(<ProcessModelVersionHistory modifiedId="finance:invoice" canRestore onChanged={onChanged} />);
    fireEvent.click(screen.getByRole('button', { name: 'Version History' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard Changes' }));
    const confirmation = screen.getByRole('alertdialog');
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Discard Changes' }));
    expect(await within(confirmation).findByRole('alert')).toHaveTextContent('Reload the model before trying again.');
    expect(onChanged).not.toHaveBeenCalled();
  });
});
