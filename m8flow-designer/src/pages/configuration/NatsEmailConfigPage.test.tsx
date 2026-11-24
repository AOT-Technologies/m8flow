import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
}));

const mockFetchNatsEmailStatus = vi.fn();
vi.mock('@/lib/secretsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/secretsApi')>('@/lib/secretsApi');
  return {
    ...actual,
    fetchNatsEmailStatus: (...args: unknown[]) => mockFetchNatsEmailStatus(...args),
  };
});

const mockFetchNamedValues = vi.fn();
const mockCreateNamedValue = vi.fn();
const mockUpdateNamedValue = vi.fn();
vi.mock('@/lib/namedValuesApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/namedValuesApi')>('@/lib/namedValuesApi');
  return {
    ...actual,
    fetchNamedValues: (...args: unknown[]) => mockFetchNamedValues(...args),
    createNamedValue: (...args: unknown[]) => mockCreateNamedValue(...args),
    updateNamedValue: (...args: unknown[]) => mockUpdateNamedValue(...args),
  };
});

/** What Configure NATS sends for one key: a sensitive configuration variable. */
const sensitive = (name: string, value: string) => [{ name, value, is_sensitive: true }, null];

const FROM_EMAIL_VARIABLE = {
  id: 'var-from',
  tenantId: 't1',
  name: 'NATS_SMTP_FROM_EMAIL',
  description: null,
  isSensitive: true,
  isConfigured: true,
  value: null,
  createdAt: null,
  updatedAt: null,
};

import NatsEmailConfigPage from './NatsEmailConfigPage';

const STATUS = {
  configured: false,
  requiredKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optionalKeys: ['NATS_SMTP_PORT', 'NATS_SMTP_PASSWORD'],
  missingKeys: ['NATS_SMTP_HOST'],
  unreadableKeys: ['NATS_SMTP_FROM_EMAIL'],
  configuredKeys: ['NATS_SMTP_PORT'],
  waitingCount: 2,
};

const MANAGE: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: 't1',
  isSuperAdmin: false,
  canReadSecrets: true,
  canCreateNamedValues: true,
  canUpdateNamedValues: true,
};

function renderPage(context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={['/configuration/nats']}>
      <Routes>
        <Route path="/configuration/nats" element={<NatsEmailConfigPage />} />
        <Route path="/configuration/named-values" element={<p data-testid="named-values-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('NatsEmailConfigPage', () => {
  beforeEach(() => {
    mockFetchNamedValues.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows each NATS_SMTP_* variable with its saved state and the waiting emails', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue(STATUS);
    renderPage(MANAGE);

    expect(await screen.findByTestId('nats-email-state-port')).toHaveTextContent('Saved');
    // Unset fields carry no badge.
    expect(screen.queryByTestId('nats-email-state-host')).not.toBeInTheDocument();
    expect(screen.getByTestId('nats-email-state-fromEmail')).toHaveTextContent("Can't be read");
    expect(screen.getByTestId('nats-email-waiting')).toHaveTextContent('2');
    // Secret values are never read back, so a saved field starts empty.
    expect(screen.getByTestId('nats-email-port')).toHaveValue('');
  });

  it('saves sensitive configuration variables: creates new ones, updates existing ones, skips blanks', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue(STATUS);
    mockFetchNamedValues.mockResolvedValue([FROM_EMAIL_VARIABLE]);
    mockCreateNamedValue.mockResolvedValue({});
    mockUpdateNamedValue.mockResolvedValue({});
    renderPage(MANAGE);

    fireEvent.change(await screen.findByTestId('nats-email-host'), { target: { value: ' smtp.example.com ' } });
    fireEvent.change(screen.getByTestId('nats-email-fromEmail'), { target: { value: 'noreply@example.com' } });
    // The tenant already has settings, so unset on/off fields start at off: that is what the
    // worker uses for a missing key, and saving must not switch STARTTLS on behind the user's back.
    expect(screen.getByTestId('nats-email-starttls')).toHaveValue('false');
    expect(screen.getByTestId('nats-email-ssl')).toHaveValue('false');
    fireEvent.click(screen.getByTestId('nats-email-save'));

    // A full save returns to Configuration variables.
    expect(await screen.findByTestId('named-values-page')).toBeInTheDocument();
    expect(mockCreateNamedValue).toHaveBeenCalledWith(...sensitive('NATS_SMTP_HOST', 'smtp.example.com'));
    expect(mockCreateNamedValue).toHaveBeenCalledWith(...sensitive('NATS_SMTP_STARTTLS', 'false'));
    expect(mockCreateNamedValue).toHaveBeenCalledWith(...sensitive('NATS_SMTP_SSL', 'false'));
    // The from address already exists as a variable, so it is updated, not created.
    expect(mockUpdateNamedValue).toHaveBeenCalledWith(
      'var-from',
      { value: 'noreply@example.com', is_sensitive: true },
      null,
    );
    expect(mockCreateNamedValue).toHaveBeenCalledTimes(3);
    expect(mockUpdateNamedValue).toHaveBeenCalledTimes(1);
  });

  it('requires unsaved required fields and checks formats before saving anything', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue(STATUS);
    renderPage(MANAGE);

    fireEvent.change(await screen.findByTestId('nats-email-host'), { target: { value: 'https://smtp.example.com' } });
    fireEvent.change(screen.getByTestId('nats-email-port'), { target: { value: '70000' } });
    fireEvent.click(screen.getByTestId('nats-email-save'));

    expect(await screen.findByText(/without a scheme or port/)).toBeInTheDocument();
    expect(screen.getByText('Enter a port between 1 and 65535.')).toBeInTheDocument();
    // From address is unreadable, not saved, so it is still required.
    expect(screen.getByText('Enter a value.')).toBeInTheDocument();
    expect(mockCreateNamedValue).not.toHaveBeenCalled();
    expect(mockUpdateNamedValue).not.toHaveBeenCalled();
  });

  it('is read-only for a role that cannot create and update configuration variables', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue(STATUS);
    renderPage({ ...MANAGE, canCreateNamedValues: false, canUpdateNamedValues: false });

    expect(await screen.findByTestId('nats-email-host')).toBeDisabled();
    expect(screen.queryByTestId('nats-email-save')).not.toBeInTheDocument();
    expect(screen.getByText(/cannot change them/)).toBeInTheDocument();
  });

  it('offers to keep a saved on/off value instead of a default', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({ ...STATUS, configuredKeys: ['NATS_SMTP_STARTTLS'] });
    renderPage(MANAGE);

    const starttls = await screen.findByTestId('nats-email-starttls');
    expect(starttls).toHaveValue('');
    expect(screen.getByRole('option', { name: 'Keep saved value' })).toBeInTheDocument();
  });

  it('stays on the page and keeps unsaved input when a save fails', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({ ...STATUS, unreadableKeys: [], configuredKeys: ['NATS_SMTP_FROM_EMAIL'] });
    mockCreateNamedValue.mockRejectedValueOnce(new Error('boom'));
    renderPage(MANAGE);

    fireEvent.change(await screen.findByTestId('nats-email-host'), { target: { value: 'smtp.example.com' } });
    fireEvent.click(screen.getByTestId('nats-email-save'));

    expect(await screen.findByText('Could not save NATS_SMTP_HOST: boom')).toBeInTheDocument();
    expect(screen.queryByTestId('named-values-page')).not.toBeInTheDocument();
    expect(screen.getByTestId('nats-email-host')).toHaveValue('smtp.example.com');
  });

  it('starts on/off fields at their defaults on a first-time setup', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({ ...STATUS, unreadableKeys: [], configuredKeys: [] });
    renderPage(MANAGE);

    expect(await screen.findByTestId('nats-email-starttls')).toHaveValue('true');
    expect(screen.getByTestId('nats-email-ssl')).toHaveValue('false');
    expect(screen.getByRole('option', { name: 'On (default)' })).toBeInTheDocument();
  });

  it('does not offer to keep an unreadable on/off value', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({ ...STATUS, unreadableKeys: ['NATS_SMTP_STARTTLS'] });
    renderPage(MANAGE);

    expect(await screen.findByTestId('nats-email-starttls')).toHaveValue('false');
    expect(screen.queryByRole('option', { name: 'Keep saved value' })).not.toBeInTheDocument();
  });

  it('treats a whitespace-only password as blank', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({
      ...STATUS,
      unreadableKeys: [],
      configuredKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL', 'NATS_SMTP_STARTTLS', 'NATS_SMTP_SSL'],
    });
    renderPage(MANAGE);

    fireEvent.change(await screen.findByTestId('nats-email-password'), { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('nats-email-save'));

    expect(await screen.findByText('Enter at least one value to save.')).toBeInTheDocument();
    expect(mockCreateNamedValue).not.toHaveBeenCalled();
    expect(mockUpdateNamedValue).not.toHaveBeenCalled();
  });

  it('names the keys already saved when a later key fails', async () => {
    mockFetchNatsEmailStatus.mockResolvedValue({
      ...STATUS,
      unreadableKeys: [],
      configuredKeys: ['NATS_SMTP_STARTTLS', 'NATS_SMTP_SSL'],
    });
    mockCreateNamedValue.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('vault down'));
    renderPage(MANAGE);

    fireEvent.change(await screen.findByTestId('nats-email-host'), { target: { value: 'smtp.example.com' } });
    fireEvent.change(screen.getByTestId('nats-email-fromEmail'), { target: { value: 'noreply@example.com' } });
    fireEvent.click(screen.getByTestId('nats-email-save'));

    expect(
      await screen.findByText('Could not save NATS_SMTP_FROM_EMAIL: vault down Already saved: NATS_SMTP_HOST.'),
    ).toBeInTheDocument();
  });
});
