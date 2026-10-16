import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CreateProcessModelDialog } from './CreateProcessModelDialog';
import { fetchProcessGroups } from '@/lib/api';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    fetchProcessGroups: vi.fn().mockResolvedValue([
      {
        id: 'finance',
        display_name: 'Finance',
        description: '',
        model_count: 1,
        last_run_at: null,
      },
    ]),
  };
});

describe('CreateProcessModelDialog', () => {
  it('slugifies display name and omits id so the API can generate it', async () => {
    const onCreate = vi.fn().mockResolvedValue({ id: 'finance/expense-report' });
    const onCreated = vi.fn();
    render(
      <CreateProcessModelDialog
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreate={onCreate}
        onCreated={onCreated}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText('Display name')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Expense Report' },
    });
    expect(screen.getByLabelText('Identifier')).toHaveValue('expense-report');
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({
        group_id: 'finance',
        display_name: 'Expense Report',
        description: '',
      });
    });
    expect(onCreated).toHaveBeenCalledWith('finance:expense-report');
  });

  it('sends a manually edited identifier', async () => {
    const onCreate = vi.fn().mockResolvedValue({ id: 'finance/expenses-v2' });
    render(
      <CreateProcessModelDialog
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreate={onCreate}
        onCreated={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText('Display name')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Expense Report' },
    });
    fireEvent.change(screen.getByLabelText('Identifier'), {
      target: { value: 'expenses-v2' },
    });
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Expenses' },
    });
    expect(screen.getByLabelText('Identifier')).toHaveValue('expenses-v2');
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({
        group_id: 'finance',
        id: 'expenses-v2',
        display_name: 'Expenses',
        description: '',
      });
    });
  });

  it('shows a load error, not the "no groups" create button, when the group fetch fails', async () => {
    vi.mocked(fetchProcessGroups).mockRejectedValueOnce(new Error('boom'));
    render(
      <CreateProcessModelDialog
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreate={vi.fn()}
        onCreated={vi.fn()}
        onCreateProcessGroup={vi.fn()}
      />,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('load process groups');
    expect(screen.queryByTestId('create-process-model-new-group-button')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
  });
});
