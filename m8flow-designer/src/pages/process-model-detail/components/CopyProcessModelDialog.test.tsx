import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CopyProcessModelDialog } from './CopyProcessModelDialog';

describe('CopyProcessModelDialog', () => {
  it('submits a new leaf id and display name', async () => {
    const onCopy = vi.fn().mockResolvedValue({ id: 'finance/invoice-approval-copy' });
    const onCopied = vi.fn();
    render(
      <CopyProcessModelDialog
        open
        onClose={vi.fn()}
        defaultLeaf="invoice-approval-copy"
        defaultDisplayName="Invoice Approval (copy)"
        onCopy={onCopy}
        onCopied={onCopied}
      />,
    );

    expect(screen.getByLabelText('Process model ID')).toHaveValue('invoice-approval-copy');
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Invoice Approval copy' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Copy process model' }));
    await waitFor(() => {
      expect(onCopy).toHaveBeenCalledWith({
        id: 'invoice-approval-copy',
        display_name: 'Invoice Approval copy',
      });
    });
    expect(onCopied).toHaveBeenCalledWith('finance:invoice-approval-copy');
  });
});
