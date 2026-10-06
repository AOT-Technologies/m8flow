import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
}));

const mockFetchNatsApiKeys = vi.fn();
const mockCreateNatsApiKey = vi.fn();
const mockRevokeNatsApiKey = vi.fn();
vi.mock('@/lib/natsTokensApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/natsTokensApi')>('@/lib/natsTokensApi');
  return {
    ...actual,
    fetchNatsApiKeys: (...args: unknown[]) => mockFetchNatsApiKeys(...args),
    createNatsApiKey: (...args: unknown[]) => mockCreateNatsApiKey(...args),
    revokeNatsApiKey: (...args: unknown[]) => mockRevokeNatsApiKey(...args),
  };
});

import ApiKeysPage from './ApiKeysPage';

const NOW = Math.floor(Date.now() / 1000);
const ACTIVE = { id: 'a1', label: 'Billing webhook', scope: 'billing/paid,hr/onboard', createdAtInSeconds: NOW - 60, createdBy: 'alice' };
const EXPIRED = { id: 'e1', label: 'Old CRM', scope: null, expiresAtInSeconds: NOW - 10 };
const REVOKED = { id: 'r1', label: 'Leaked key', revokedAtInSeconds: NOW - 100 };

const TENANT_ADMIN: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: null,
  isSuperAdmin: false,
  canReadNatsApiKeys: true,
  canManageNatsApiKeys: true,
};

function renderPage(context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(<ApiKeysPage />);
}

function rowFor(label: string) {
  return screen.getByText(label).closest('[role="row"]') as HTMLElement;
}

describe('ApiKeysPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('asks an All-Tenants super-admin to pick a tenant instead of fetching', () => {
    renderPage({ ...TENANT_ADMIN, isSuperAdmin: true });
    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
    expect(mockFetchNatsApiKeys).not.toHaveBeenCalled();
  });

  it('scopes the list to the super-admin sidebar tenant', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([]);
    renderPage({ ...TENANT_ADMIN, isSuperAdmin: true, scopedTenantId: 't1', selectedTenantId: 't1' });
    expect(await screen.findByText('No API keys in this tenant yet.')).toBeInTheDocument();
    expect(mockFetchNatsApiKeys).toHaveBeenCalledWith('t1');
  });

  it('shows active, expired and revoked status, read-only without manage', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([ACTIVE, EXPIRED, REVOKED]);
    renderPage({ ...TENANT_ADMIN, canManageNatsApiKeys: false });

    expect(await screen.findByText('Billing webhook')).toBeInTheDocument();
    expect(within(rowFor('Billing webhook')).getByText('Active')).toBeInTheDocument();
    expect(within(rowFor('Billing webhook')).getByText('billing/paid, hr/onboard')).toBeInTheDocument();
    expect(within(rowFor('Old CRM')).getByText('Expired')).toBeInTheDocument();
    expect(within(rowFor('Old CRM')).getByText('Any process')).toBeInTheDocument();
    expect(within(rowFor('Leaked key')).getByText('Revoked')).toBeInTheDocument();
    expect(mockFetchNatsApiKeys).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('button', { name: /Create API key/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument();
  });

  it('creates a key, shows the token once, and forgets it on Done', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([]);
    mockCreateNatsApiKey.mockResolvedValue({ ...ACTIVE, id: 'n1', label: 'CRM', token: 'm8f_n1.s3cret' });
    renderPage(TENANT_ADMIN);

    fireEvent.click(await screen.findByRole('button', { name: /Create API key/ }));
    fireEvent.change(screen.getByTestId('api-key-label'), { target: { value: '  CRM  ' } });
    fireEvent.change(screen.getByTestId('api-key-scope'), { target: { value: 'a/b, ,c/d ' } });
    fireEvent.change(screen.getByTestId('api-key-expiry'), { target: { value: 'never' } });
    fireEvent.click(screen.getByTestId('api-key-create'));

    expect(await screen.findByTestId('api-key-token')).toHaveTextContent('m8f_n1.s3cret');
    expect(mockCreateNatsApiKey).toHaveBeenCalledWith(
      { label: 'CRM', expiresInDays: null, scope: ['a/b', 'c/d'] },
      null,
    );
    await waitFor(() => expect(mockFetchNatsApiKeys).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText('m8f_n1.s3cret')).not.toBeInTheDocument();
  });

  it('falls back to manual copy when the clipboard rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new DOMException('Write permission denied.', 'NotAllowedError'));
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    mockFetchNatsApiKeys.mockResolvedValue([]);
    mockCreateNatsApiKey.mockResolvedValue({ id: 'n1', label: 'CRM', token: 'm8f_n1.s3cret' });
    renderPage(TENANT_ADMIN);

    fireEvent.click(await screen.findByRole('button', { name: /Create API key/ }));
    fireEvent.change(screen.getByTestId('api-key-label'), { target: { value: 'CRM' } });
    fireEvent.click(screen.getByTestId('api-key-create'));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy' }));

    expect(await screen.findByText("Couldn't copy automatically. Select the key and copy it yourself.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith('m8f_n1.s3cret');
    expect(screen.queryByRole('button', { name: 'Copied' })).not.toBeInTheDocument();
    expect(screen.getByTestId('api-key-token')).toHaveTextContent('m8f_n1.s3cret');
  });

  it('defaults expiry to 90 days and omits an empty scope', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([]);
    mockCreateNatsApiKey.mockResolvedValue({ id: 'n1', label: 'CRM', token: 't' });
    renderPage(TENANT_ADMIN);

    fireEvent.click(await screen.findByRole('button', { name: /Create API key/ }));
    expect(screen.getByTestId('api-key-create')).toBeDisabled();
    fireEvent.change(screen.getByTestId('api-key-label'), { target: { value: 'CRM' } });
    fireEvent.click(screen.getByTestId('api-key-create'));

    await waitFor(() =>
      expect(mockCreateNatsApiKey).toHaveBeenCalledWith({ label: 'CRM', expiresInDays: 90 }, null),
    );
  });

  it('keeps the form open with the server reason when create fails', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([]);
    mockCreateNatsApiKey.mockRejectedValue(
      new ApiError('/v1.0/m8flow/nats-tokens', 400, 'POST', 'expiresInDays must be one of: 30, 90, 365'),
    );
    renderPage(TENANT_ADMIN);

    fireEvent.click(await screen.findByRole('button', { name: /Create API key/ }));
    fireEvent.change(screen.getByTestId('api-key-label'), { target: { value: 'CRM' } });
    fireEvent.click(screen.getByTestId('api-key-create'));

    expect(await screen.findByTestId('api-key-create-error')).toHaveTextContent('expiresInDays must be one of');
    expect(screen.getByTestId('api-key-create')).not.toBeDisabled();
    expect(screen.queryByTestId('api-key-created')).not.toBeInTheDocument();
  });

  it('revokes after confirm and offers no revoke on an already-revoked key', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([ACTIVE, REVOKED]);
    mockRevokeNatsApiKey.mockResolvedValue(undefined);
    renderPage(TENANT_ADMIN);

    await screen.findByText('Billing webhook');
    expect(within(rowFor('Leaked key')).queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument();

    fireEvent.click(within(rowFor('Billing webhook')).getByRole('button', { name: 'Revoke' }));
    expect(await screen.findByRole('heading', { name: 'Revoke API key?' })).toBeInTheDocument();
    const revokeButtons = screen.getAllByRole('button', { name: 'Revoke' });
    fireEvent.click(revokeButtons[revokeButtons.length - 1]);

    await waitFor(() => expect(mockRevokeNatsApiKey).toHaveBeenCalledWith('a1', null));
    await waitFor(() => expect(mockFetchNatsApiKeys).toHaveBeenCalledTimes(2));
  });

  it('closes the revoke dialog on Cancel without revoking', async () => {
    mockFetchNatsApiKeys.mockResolvedValue([ACTIVE]);
    renderPage(TENANT_ADMIN);

    await screen.findByText('Billing webhook');
    fireEvent.click(within(rowFor('Billing webhook')).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockRevokeNatsApiKey).not.toHaveBeenCalled();
  });
});
