import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const getSmtpStatus = vi.hoisted(() => vi.fn());

vi.mock('../../services/ExternalFormNotificationService', () => ({
  getSmtpStatus,
}));

// The components import hooks from the properties panel's bundled preact. Under Vitest
// the app renders with real React (vite.config disables the preact alias), so map that
// subpath onto React's equivalents.
vi.mock('@bpmn-io/properties-panel/preact/hooks', async () => {
  const react = await import('react');
  return { useEffect: react.useEffect, useState: react.useState };
});

import {
  ExternalFormSmtpLabel,
  ExternalFormSmtpStatus,
} from './ExternalFormSmtpStatus';

const CONFIGURED = {
  configured: true,
  required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optional_keys: [],
  missing_required_keys: [],
  unreadable_keys: [],
  reason: null,
  configured_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
};

const UNCONFIGURED = {
  ...CONFIGURED,
  configured: false,
  missing_required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  configured_keys: [],
  reason: 'SMTP is not configured for this tenant.',
};

beforeEach(() => {
  getSmtpStatus.mockReset();
});

describe('ExternalFormSmtpLabel', () => {
  it('marks the group label when the tenant cannot send email', async () => {
    // The label is the only part of the group visible while it is collapsed, so this
    // marker is what actually surfaces the problem to a modeler.
    getSmtpStatus.mockResolvedValue(UNCONFIGURED);

    render(<ExternalFormSmtpLabel label="Web Form (External Form)" />);

    const marked = await screen.findByTestId('external-form-smtp-label');
    expect(marked).toHaveTextContent('Web Form (External Form)');
    expect(marked).toHaveTextContent('⚠');
  });

  it('leaves the label untouched when SMTP is configured', async () => {
    getSmtpStatus.mockResolvedValue(CONFIGURED);

    render(<ExternalFormSmtpLabel label="Web Form (External Form)" />);

    await waitFor(() => expect(getSmtpStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('external-form-smtp-label')).toBeNull();
    expect(screen.getByText('Web Form (External Form)')).toBeInTheDocument();
  });

  it('leaves the label untouched when the status cannot be read', async () => {
    getSmtpStatus.mockRejectedValue(new Error('403'));

    render(<ExternalFormSmtpLabel label="Web Form (External Form)" />);

    await waitFor(() => expect(getSmtpStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('external-form-smtp-label')).toBeNull();
    expect(screen.getByText('Web Form (External Form)')).toBeInTheDocument();
  });
});

describe('ExternalFormSmtpStatus', () => {
  it('lists the missing secrets', async () => {
    getSmtpStatus.mockResolvedValue(UNCONFIGURED);

    render(<ExternalFormSmtpStatus />);

    const warning = await screen.findByTestId('external-form-smtp-warning');
    expect(warning).toHaveTextContent('NATS_SMTP_HOST');
    expect(warning).toHaveTextContent('NATS_SMTP_FROM_EMAIL');
    expect(warning).toHaveTextContent('Configuration > Secrets');
  });

  it('renders nothing when SMTP is configured', async () => {
    getSmtpStatus.mockResolvedValue(CONFIGURED);

    render(<ExternalFormSmtpStatus />);

    await waitFor(() => expect(getSmtpStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('external-form-smtp-warning')).toBeNull();
  });

  it('renders nothing when the status call fails', async () => {
    // A failed or forbidden status call must never break the modeler.
    getSmtpStatus.mockRejectedValue(new Error('403'));

    render(<ExternalFormSmtpStatus />);

    await waitFor(() => expect(getSmtpStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('external-form-smtp-warning')).toBeNull();
  });

  it('renders nothing when getSmtpStatus throws synchronously', async () => {
    getSmtpStatus.mockImplementation(() => {
      throw new Error('boom');
    });

    expect(() => render(<ExternalFormSmtpStatus />)).not.toThrow();
    expect(screen.queryByTestId('external-form-smtp-warning')).toBeNull();
  });

  it('tolerates a payload with no missing-key list', async () => {
    getSmtpStatus.mockResolvedValue({
      ...UNCONFIGURED,
      missing_required_keys: undefined,
    });

    render(<ExternalFormSmtpStatus />);

    const warning = await screen.findByTestId('external-form-smtp-warning');
    expect(warning).toBeInTheDocument();
  });
});
