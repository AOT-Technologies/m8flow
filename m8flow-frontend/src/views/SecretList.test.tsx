import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import SecretList from './SecretList';

const h = vi.hoisted(() => ({
  ability: { can: () => true },
  targetUris: {
    authenticationListPath: '/authentications',
    secretListPath: '/secrets',
  },
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(() => ({
    selectedTenantId: '',
    setSelectedTenantId: vi.fn(),
  })),
}));

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: () => ({
    ability: h.ability,
    permissionsLoaded: true,
  }),
}));

vi.mock('../hooks/UriListForPermissions', () => ({
  useUriListForPermissions: () => ({
    targetUris: h.targetUris,
  }),
}));

vi.mock('../helpers', () => ({
  getPageInfoFromSearchParams: () => ({ page: 1, perPage: 10 }),
}));

vi.mock('../components/PaginationForTable', () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div data-testid="pagination-mock">{tableToDisplay}</div>
  ),
}));

vi.mock('@casl/react', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('react-icons/md', () => ({
  MdDelete: () => <span data-testid="delete-icon" />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../services/ExternalFormNotificationService', () => ({
  getSmtpStatus: vi.fn(),
  clearSmtpStatusCache: vi.fn(),
}));

import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';
import {
  getSmtpStatus,
  clearSmtpStatusCache,
} from '../services/ExternalFormNotificationService';

const SMTP_CONFIGURED = {
  configured: true,
  required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optional_keys: [],
  missing_required_keys: [],
  unreadable_keys: [],
  reason: null,
  configured_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
};

function stubSmtpStatus(overrides: Record<string, unknown> = {}) {
  vi.mocked(getSmtpStatus).mockResolvedValue({
    ...SMTP_CONFIGURED,
    ...overrides,
  } as any);
}

function stubSecretsList() {
  vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
    opts.successCallback({
      results: [
        {
          id: 1,
          key: 'api-key',
          username: 'editor',
          tenantName: 'Acme',
          tenantId: 'tenant-a',
        },
      ],
      pagination: { total: 1, pages: 1 },
    });
  });
}

function renderList() {
  return render(
    <MemoryRouter>
      <SecretList />
    </MemoryRouter>,
  );
}

describe('SecretList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubSecretsList();
    stubSmtpStatus();
  });

  it('sends tenantId and shows the tenant column for super-admin', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/secrets?per_page=10&page=1&tenantId=tenant-a',
      }),
    );
    expect(screen.getByTestId('secret-list-tenant-cell')).toHaveTextContent(
      'Acme',
    );
    // Let the async SMTP banner settle inside the test rather than after it.
    await screen.findByTestId('external-form-smtp-configured');
  });

  it('omits tenantId and the tenant column for non-super-admin', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/secrets?per_page=10&page=1',
      }),
    );
    expect(screen.queryByTestId('secret-list-tenant-cell')).toBeNull();
    await screen.findByTestId('external-form-smtp-configured');
  });
});

describe('SecretList external form email banner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubSecretsList();
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('names the missing NATS_SMTP_* secrets when the tenant is unconfigured', async () => {
    // Nothing else on this page names these keys, so without the banner a tenant admin
    // has no way to discover why external form emails silently never arrive.
    stubSmtpStatus({
      configured: false,
      missing_required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      reason: 'SMTP is not configured for this tenant.',
    });

    renderList();

    const banner = await screen.findByTestId(
      'external-form-smtp-not-configured',
    );
    expect(banner).toHaveTextContent('external_form_smtp_missing_hint');
    expect(banner).toHaveTextContent('NATS_SMTP_HOST');
    expect(banner).toHaveTextContent('NATS_SMTP_FROM_EMAIL');
  });

  it('shows the backend reason when a secret is unreadable rather than missing', async () => {
    // Re-entering the key is not the fix here, so the generic "these are missing"
    // headline would send the admin down the wrong path.
    stubSmtpStatus({
      configured: false,
      missing_required_keys: ['NATS_SMTP_FROM_EMAIL'],
      unreadable_keys: ['NATS_SMTP_FROM_EMAIL'],
      reason:
        'SMTP secrets exist but could not be read (blank value, or the backend encryption key changed): NATS_SMTP_FROM_EMAIL',
    });

    renderList();

    const banner = await screen.findByTestId(
      'external-form-smtp-not-configured',
    );
    expect(banner).toHaveTextContent('encryption key changed');
    expect(banner).not.toHaveTextContent('external_form_smtp_missing_hint');
  });

  it('reports the configured case without warning', async () => {
    stubSmtpStatus();

    renderList();

    expect(
      await screen.findByTestId('external-form-smtp-configured'),
    ).toHaveTextContent('external_form_smtp_configured_hint');
    expect(
      screen.queryByTestId('external-form-smtp-not-configured'),
    ).toBeNull();
  });

  it('hides the banner when the status cannot be read', async () => {
    // Covers both a 403 for a user without the permission and the 400 a super admin
    // gets before choosing a tenant. Neither may break the Secrets page.
    vi.mocked(getSmtpStatus).mockRejectedValue(new Error('403'));

    renderList();

    expect(await screen.findByText('secrets')).toBeInTheDocument();
    expect(
      screen.queryByTestId('external-form-smtp-not-configured'),
    ).toBeNull();
    expect(screen.queryByTestId('external-form-smtp-configured')).toBeNull();
  });

  it('asks for the selected tenant status as a super admin', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    stubSmtpStatus();

    renderList();

    await screen.findByTestId('external-form-smtp-configured');
    expect(clearSmtpStatusCache).toHaveBeenCalledWith('tenant-a');
    expect(getSmtpStatus).toHaveBeenCalledWith('tenant-a', { force: true });
  });

  it('does not pass a tenant id for a normal tenant user', async () => {
    stubSmtpStatus();

    renderList();

    await screen.findByTestId('external-form-smtp-configured');
    expect(clearSmtpStatusCache).toHaveBeenCalledWith(null);
    expect(getSmtpStatus).toHaveBeenCalledWith(null, { force: true });
  });
});
