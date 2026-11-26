import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { ExternalFormEmail } from '@/lib/externalFormNotificationsApi';

import { ProcessInstanceExternalFormEmailsTable } from './ProcessInstanceExternalFormEmailsTable';

const fetchExternalFormEmails = vi.fn();
const resendExternalFormEmail = vi.fn();

vi.mock('@/lib/externalFormNotificationsApi', () => ({
  fetchExternalFormEmails: (...args: unknown[]) => fetchExternalFormEmails(...args),
  resendExternalFormEmail: (...args: unknown[]) => resendExternalFormEmail(...args),
}));

function row(overrides: Partial<ExternalFormEmail>): ExternalFormEmail {
  return {
    id: 1,
    process_instance_id: 7,
    task_guid: 'g1',
    task_name: 'approve',
    task_title: 'Approve request',
    email: 'alice@example.test',
    status: 'notified',
    effective_status: 'notified',
    stuck_sending: false,
    resendable: true,
    attempts: 1,
    last_error: null,
    created_at: null,
    updated_at: null,
    notified_at_in_seconds: 1_783_380_927,
    expires_at_in_seconds: 1_783_985_727,
    ...overrides,
  };
}

function list(rows: ExternalFormEmail[]) {
  return { results: rows, pagination: { count: rows.length, total: rows.length, pages: 1, page: 1 } };
}

describe('ProcessInstanceExternalFormEmailsTable', () => {
  beforeEach(() => {
    fetchExternalFormEmails.mockReset();
    resendExternalFormEmail.mockReset();
  });

  it('labels rows by effective status and flags a stuck send', async () => {
    fetchExternalFormEmails.mockResolvedValue(
      list([
        row({ id: 1, status: 'notified', effective_status: 'expired' }),
        row({ id: 2, email: 'bob@example.test', status: 'sending', effective_status: 'sending', stuck_sending: true }),
        row({ id: 3, email: 'carol@example.test', status: 'superseded', effective_status: 'superseded', resendable: false }),
        row({ id: 4, email: 'dan@example.test', status: 'smtp_unconfigured', effective_status: 'smtp_unconfigured', last_error: 'SMTP is not configured' }),
      ]),
    );

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} tenantId="t1" canResend />);

    expect(await screen.findByText('Link expired')).toBeInTheDocument();
    expect(screen.getByText('Sending')).toBeInTheDocument();
    expect(screen.getByText(/taking longer than expected/)).toBeInTheDocument();
    expect(screen.getByText('Done by someone else')).toBeInTheDocument();
    expect(screen.getByText('Email not set up')).toBeInTheDocument();
    expect(screen.getByText('SMTP is not configured')).toBeInTheDocument();
    // Resend only on resendable rows (carol's task was completed by someone else).
    expect(screen.getAllByRole('button', { name: 'Resend' })).toHaveLength(3);
    expect(fetchExternalFormEmails).toHaveBeenCalledWith(7, 't1');
  });

  it('hides Resend without the resend permission', async () => {
    fetchExternalFormEmails.mockResolvedValue(list([row({})]));

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} canResend={false} />);

    expect(await screen.findByText('alice@example.test')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resend' })).not.toBeInTheDocument();
  });

  it('confirms, resends and reports success', async () => {
    const user = userEvent.setup();
    fetchExternalFormEmails.mockResolvedValue(list([row({ effective_status: 'failed', status: 'failed' })]));
    resendExternalFormEmail.mockResolvedValue({ ok: true, id: 1, status: 'pending', message: 'ok' });

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} tenantId="t1" canResend />);

    await user.click(await screen.findByRole('button', { name: 'Resend' }));
    expect(screen.getByText('Resend form link?')).toBeInTheDocument();
    expect(resendExternalFormEmail).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Resend' }));

    await waitFor(() => expect(resendExternalFormEmail).toHaveBeenCalledWith(1, 't1'));
    expect(await screen.findByText(/A new form link was issued for alice@example.test/)).toBeInTheDocument();
    expect(fetchExternalFormEmails).toHaveBeenCalledTimes(2);
  });

  it("shows the backend's reason when a resend is refused", async () => {
    const user = userEvent.setup();
    fetchExternalFormEmails.mockResolvedValue(list([row({})]));
    resendExternalFormEmail.mockRejectedValue(
      new ApiError('/resend', 409, 'POST', 'Its task is no longer open.', 'external_form_request_not_resendable'),
    );

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} canResend />);

    await user.click(await screen.findByRole('button', { name: 'Resend' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Resend' }));

    expect(await screen.findByText('Its task is no longer open.')).toBeInTheDocument();
  });

  it('explains cancelled links and shows an empty state', async () => {
    fetchExternalFormEmails.mockResolvedValue(
      list([row({ status: 'cancelled', effective_status: 'cancelled', resendable: false })]),
    );
    const view = render(<ProcessInstanceExternalFormEmailsTable instanceId={7} canResend />);
    expect(await screen.findByText(/Cancelled links no longer work/)).toBeInTheDocument();
    view.unmount();

    fetchExternalFormEmails.mockResolvedValue(list([]));
    render(<ProcessInstanceExternalFormEmailsTable instanceId={8} canResend />);
    expect(
      await screen.findByText('No external form emails have been sent for this process instance.'),
    ).toBeInTheDocument();
  });

  it('shows no sent date while sending and an unknown status as-is', async () => {
    fetchExternalFormEmails.mockResolvedValue(
      list([
        row({ id: 1, status: 'sending', effective_status: 'sending', notified_at_in_seconds: 1_783_380_927 }),
        row({ id: 2, email: 'bob@example.test', effective_status: 'bounced' as ExternalFormEmail['effective_status'] }),
      ]),
    );

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} canResend={false} />);

    expect(await screen.findByText('bounced')).toBeInTheDocument();
    expect(screen.queryByText('Waiting to send')).not.toBeInTheDocument();
    // Only bob's delivered row shows a sent date; the claim time of the sending row is hidden.
    expect(screen.getAllByText('2026-07-06 23:35')).toHaveLength(1);
  });

  it('says when only the newest emails are shown', async () => {
    fetchExternalFormEmails.mockResolvedValue({
      results: [row({})],
      pagination: { count: 1, total: 250, pages: 250, page: 1 },
    });

    render(<ProcessInstanceExternalFormEmailsTable instanceId={7} canResend={false} />);

    expect(await screen.findByText('Showing the newest 1 of 250 emails.')).toBeInTheDocument();
  });
});
