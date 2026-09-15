import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AcceptInvitationPage from './AcceptInvitationPage';

const mockValidateInvitation = vi.fn();
const mockAcceptInvitation = vi.fn();

vi.mock('@/lib/invitationsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/invitationsApi')>(
    '@/lib/invitationsApi',
  );
  return {
    ...actual,
    validateInvitation: (...args: unknown[]) => mockValidateInvitation(...args),
    acceptInvitation: (...args: unknown[]) => mockAcceptInvitation(...args),
  };
});

const VALIDATION = {
  email: 'user@example.com',
  tenant_id: 'tenant-1',
  tenant_name: 'Acme Corp',
  roles: ['editor', 'viewer'],
  expires_at_in_seconds: 123,
};

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AcceptInvitationPage />
    </MemoryRouter>,
  );
}

describe('AcceptInvitationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an error and skips validation when the token is missing', async () => {
    renderPage('/accept-invitation');

    expect(await screen.findByTestId('accept-invitation-error')).toBeInTheDocument();
    expect(mockValidateInvitation).not.toHaveBeenCalled();
  });

  it('renders the invitation metadata once the token validates', async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    renderPage('/accept-invitation?token=raw-token');

    expect(await screen.findByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('editor')).toBeInTheDocument();
    expect(screen.getByText('viewer')).toBeInTheDocument();
    expect(mockValidateInvitation).toHaveBeenCalledWith('raw-token');
  });

  it('shows the validation error when the token is invalid', async () => {
    mockValidateInvitation.mockRejectedValue(new Error('This invitation link has expired.'));
    renderPage('/accept-invitation?token=expired');

    expect(await screen.findByText('This invitation link has expired.')).toBeInTheDocument();
  });

  it('disables submit until the password is long enough and confirmation matches', async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    renderPage('/accept-invitation?token=raw-token');
    await screen.findByText('Acme Corp');

    const submit = screen.getByTestId('accept-invitation-submit');
    const password = screen.getByTestId('accept-invitation-password');
    const confirm = screen.getByTestId('accept-invitation-confirm-password');

    expect(submit).toBeDisabled();

    fireEvent.change(password, { target: { value: 'short' } });
    fireEvent.change(confirm, { target: { value: 'short' } });
    expect(submit).toBeDisabled();

    fireEvent.change(password, { target: { value: 'password123' } });
    fireEvent.change(confirm, { target: { value: 'mismatch123' } });
    expect(submit).toBeDisabled();

    fireEvent.change(confirm, { target: { value: 'password123' } });
    expect(submit).toBeEnabled();
  });

  it('activates the account on a successful accept and does not auto-login', async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    mockAcceptInvitation.mockResolvedValue({ smtp_configured: false });
    renderPage('/accept-invitation?token=raw-token');
    await screen.findByText('Acme Corp');

    fireEvent.change(screen.getByTestId('accept-invitation-password'), {
      target: { value: 'password123' },
    });
    fireEvent.change(screen.getByTestId('accept-invitation-confirm-password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByTestId('accept-invitation-submit'));

    await waitFor(() => {
      expect(mockAcceptInvitation).toHaveBeenCalledWith('raw-token', 'password123');
    });
    const goLogin = await screen.findByTestId('accept-invitation-go-login');
    expect(goLogin).toHaveAttribute('href', '/');
    expect(screen.queryByText('Sign In')).not.toBeInTheDocument();
  });

  it('shows the submit error when accepting fails', async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    mockAcceptInvitation.mockRejectedValue(new Error('Failed to activate your account.'));
    renderPage('/accept-invitation?token=raw-token');
    await screen.findByText('Acme Corp');

    fireEvent.change(screen.getByTestId('accept-invitation-password'), {
      target: { value: 'password123' },
    });
    fireEvent.change(screen.getByTestId('accept-invitation-confirm-password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByTestId('accept-invitation-submit'));

    expect(await screen.findByText('Failed to activate your account.')).toBeInTheDocument();
  });
});
