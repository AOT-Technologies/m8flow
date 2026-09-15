import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CallActivitySearchDialog, type CallActivitySearchSession } from './CallActivitySearchDialog';

const SESSION: CallActivitySearchSession = {
  processModels: [
    { id: 'finance/invoice-approval', displayName: 'Invoice Approval', groupDisplayName: 'Finance' },
    { id: 'onboarding/new-hire', displayName: 'New Hire', groupDisplayName: 'Onboarding' },
  ],
  onSelect: vi.fn(),
};

// New test file — this component had none before migrating to the shared
// Dialog primitive (see
// .scratch/m8flow-designer-optimization/issues/09-extract-input-dialog-primitives.md).
// Verifies the migration didn't regress anything and that the two new
// dismissal capabilities (Escape, outside-click) it gained actually work.
describe('CallActivitySearchDialog', () => {
  it('lists process models and selects one', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(
      <CallActivitySearchDialog session={{ ...SESSION, onSelect }} onClose={onClose} />,
    );

    expect(screen.getByRole('dialog', { name: 'Search process models' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Invoice Approval/ }));
    expect(onSelect).toHaveBeenCalledWith('finance/invoice-approval');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('filters results by search', () => {
    render(<CallActivitySearchDialog session={SESSION} onClose={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('Search by name, id, or group…'), {
      target: { value: 'onboard' },
    });
    expect(screen.getByText('New Hire')).toBeInTheDocument();
    expect(screen.queryByText('Invoice Approval')).not.toBeInTheDocument();
  });

  it('focuses the search input on open', async () => {
    render(<CallActivitySearchDialog session={SESSION} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByPlaceholderText('Search by name, id, or group…')).toHaveFocus());
  });

  it('closes on Close button, Escape, and outside click', async () => {
    const onClose = vi.fn();
    render(<CallActivitySearchDialog session={SESSION} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close search' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Same Radix dismissal mechanics as ProcessGroupsPicker.test.tsx — see
    // its comments for why `document` (not `window`) and why the
    // pointerdown listener needs a tick to attach first.
    await new Promise((resolve) => setTimeout(resolve, 0));
    const overlay = document.querySelector('[data-slot="dialog-overlay"]')!;
    fireEvent.pointerDown(overlay);
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
