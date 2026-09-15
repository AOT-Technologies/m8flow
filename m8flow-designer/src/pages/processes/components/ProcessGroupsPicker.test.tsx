import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ProcessGroupsPicker } from './ProcessGroupsPicker';
import type { ProcessGroupListItem } from '@/lib/api';

const GROUPS: ProcessGroupListItem[] = [
  {
    id: 'finance',
    display_name: 'Finance',
    description: 'Invoice approvals',
    model_count: 2,
    last_run_in_seconds: 1_700_000_000,
  },
  {
    id: 'onboarding',
    display_name: 'Onboarding',
    description: 'New-hire provisioning',
    model_count: 1,
    last_run_in_seconds: null,
  },
];

describe('ProcessGroupsPicker', () => {
  it('renders nothing when closed', () => {
    render(
      <ProcessGroupsPicker
        open={false}
        groups={GROUPS}
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
      />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('lists groups and selects one', () => {
    const onSelect = vi.fn();
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={onSelect}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Process groups' })).toBeInTheDocument();
    expect(screen.getByText('Finance')).toBeInTheDocument();
    expect(screen.getByText('No runs yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Finance/ }));
    expect(onSelect).toHaveBeenCalledWith('finance');
  });

  it('filters by search and selects All groups', () => {
    const onSelectAll = vi.fn();
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        selectedGroupId="finance"
        onClose={vi.fn()}
        onSelectAll={onSelectAll}
        onSelectGroup={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Search groups'), {
      target: { value: 'onboard' },
    });
    expect(screen.getByText('Onboarding')).toBeInTheDocument();
    expect(screen.queryByText('Finance')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /All groups/ }));
    expect(onSelectAll).toHaveBeenCalled();
  });

  it('closes on backdrop click, Close, and Escape', async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        onClose={onClose}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Backdrop dismissal is now Radix Dialog's own outside-interaction
    // detection (`DismissableLayer`), which listens for `pointerdown`
    // (deferred to the following `click`) on anything outside the dialog
    // content — not a plain `click` on a specific backdrop div, since the
    // overlay/content are independently fixed-positioned siblings under
    // Radix rather than nested divs (see ProcessGroupsPicker.tsx's own
    // comment on this). Its outside-pointerdown listener also only attaches
    // after a `setTimeout(0)` on mount (so the same click that opens a
    // dialog can't immediately close it) — let that resolve first.
    await new Promise((resolve) => setTimeout(resolve, 0));
    const overlay = document.querySelector('[data-slot="dialog-overlay"]')!;
    fireEvent.pointerDown(overlay);
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(2);

    // Radix's Escape handling listens on `document` (with `capture: true`),
    // not `window` — the manual listener this replaced used `window`, which
    // is why the old assertions fired on `window` instead.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);

    rerender(
      <ProcessGroupsPicker
        open={false}
        groups={GROUPS}
        onClose={onClose}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
      />,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('hides New group unless canManage', () => {
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /New group/i })).not.toBeInTheDocument();
  });

  it('creates a group and returns to the list', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        canManage
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
        onCreateGroup={onCreate}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /New group/i }));
    expect(screen.getByRole('heading', { name: 'New process group' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Process group id'), { target: { value: 'legal' } });
    fireEvent.change(screen.getByLabelText('Process group display name'), {
      target: { value: 'Legal' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create group' }));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({
        id: 'legal',
        display_name: 'Legal',
        description: '',
      });
    });
    expect(screen.getByRole('heading', { name: 'Process groups' })).toBeInTheDocument();
  });

  it('prefixes a nested id from the selected group', () => {
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        selectedGroupId="finance"
        canManage
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={vi.fn()}
        onCreateGroup={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /New group/i }));
    expect(screen.getByLabelText('Process group id')).toHaveValue('finance/');
  });

  it('edits and deletes a group without selecting it', async () => {
    const onSelect = vi.fn();
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(
      <ProcessGroupsPicker
        open
        groups={GROUPS}
        canManage
        onClose={vi.fn()}
        onSelectAll={vi.fn()}
        onSelectGroup={onSelect}
        onUpdateGroup={onUpdate}
        onDeleteGroup={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Edit Finance' }));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Process group display name'), {
      target: { value: 'Finance Ops' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save group' }));
    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith('finance', {
        display_name: 'Finance Ops',
        description: 'Invoice approvals',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Onboarding' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete group' }));
    await waitFor(() => {
      expect(onDelete).toHaveBeenCalledWith('onboarding');
    });
    expect(onSelect).not.toHaveBeenCalled();
  });
});
