import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SmtpConfigWarning } from './SmtpConfigWarning';

const fetchSmtpStatus = vi.fn();
let canReadSecrets = true;

vi.mock('@/lib/externalFormNotificationsApi', () => ({
  fetchSmtpStatus: (...args: unknown[]) => fetchSmtpStatus(...args),
}));
vi.mock('@/components/session/hooks', () => ({
  useCapabilities: () => ({ canReadSecrets }),
}));

function status(overrides: Record<string, unknown>) {
  return {
    configured: false,
    required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
    optional_keys: [],
    missing_required_keys: [],
    unreadable_keys: [],
    reason: null,
    configured_keys: [],
    ...overrides,
  };
}

describe('SmtpConfigWarning', () => {
  beforeEach(() => {
    fetchSmtpStatus.mockReset();
    canReadSecrets = true;
  });

  it('names the missing and unreadable email settings', async () => {
    fetchSmtpStatus.mockResolvedValue(
      status({
        missing_required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
        unreadable_keys: ['NATS_SMTP_FROM_EMAIL'],
      }),
    );

    render(<SmtpConfigWarning tenantId={null} isSuperAdmin={false} />);

    expect(await screen.findByText('External form emails cannot be sent')).toBeInTheDocument();
    expect(screen.getByText('Missing email settings: NATS_SMTP_HOST')).toBeInTheDocument();
    expect(screen.getByText('Email settings that could not be read: NATS_SMTP_FROM_EMAIL')).toBeInTheDocument();
    expect(fetchSmtpStatus).toHaveBeenCalledWith(null);
  });

  it('shows nothing once email is configured', async () => {
    fetchSmtpStatus.mockResolvedValue(status({ configured: true }));

    render(<SmtpConfigWarning tenantId={null} isSuperAdmin={false} />);

    await waitFor(() => expect(fetchSmtpStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('smtp-config-warning')).not.toBeInTheDocument();
  });

  it('does not ask without secrets read access, or for a super-admin with no tenant', () => {
    canReadSecrets = false;
    const view = render(<SmtpConfigWarning tenantId="t1" isSuperAdmin={false} />);
    view.unmount();
    canReadSecrets = true;
    render(<SmtpConfigWarning tenantId={null} isSuperAdmin />);

    expect(fetchSmtpStatus).not.toHaveBeenCalled();
  });

  it("passes a super-admin's selected tenant", async () => {
    fetchSmtpStatus.mockResolvedValue(status({ configured: true }));

    render(<SmtpConfigWarning tenantId="t2" isSuperAdmin />);

    await waitFor(() => expect(fetchSmtpStatus).toHaveBeenCalledWith('t2'));
  });
});
