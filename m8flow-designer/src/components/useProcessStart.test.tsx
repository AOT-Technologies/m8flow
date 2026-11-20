// SPDX-License-Identifier: Apache-2.0

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import '@/i18n';
import { startProcessInstance, type CollaborationParticipant } from '@/lib/api';
import { useProcessStart } from './useProcessStart';

vi.mock('@/lib/api', () => ({ startProcessInstance: vi.fn().mockResolvedValue({ id: 12 }) }));

function Harness({ participants }: { participants?: CollaborationParticipant[] }) {
  const { start, picker } = useProcessStart();
  return (
    <>
      <button onClick={() => void start('orders:collaboration', 'orders', participants)}>Open start</button>
      {picker}
    </>
  );
}

it('starts single-process models directly', async () => {
  vi.clearAllMocks();
  render(<Harness />);
  await userEvent.click(screen.getByRole('button', { name: 'Open start' }));
  expect(startProcessInstance).toHaveBeenCalledWith('orders:collaboration', 'orders');
});

it('selects a manual pool and forwards the exact correlation key', async () => {
  vi.clearAllMocks();
  render(<Harness participants={[
    { id: 'Order', name: 'Order', startable: true },
    { id: 'Fulfilment', name: 'Fulfilment', startable: false },
  ]} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Open start' }));
  expect(startProcessInstance).not.toHaveBeenCalled();
  expect(screen.getByRole('option', { name: /Fulfilment/ })).toBeDisabled();
  await user.selectOptions(screen.getByRole('combobox', { name: 'Executable pool' }), 'Order');
  await user.type(screen.getByLabelText(/Correlation key/), 'Order 123');
  await user.click(screen.getByRole('button', { name: 'Start' }));
  expect(startProcessInstance).toHaveBeenCalledWith('orders:collaboration', 'orders', {
    bpmn_process_id: 'Order',
    collaboration_correlation_key: 'Order 123',
  });
});
