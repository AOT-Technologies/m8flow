import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';

// The Secrets page is where an admin can actually fix missing SMTP configuration, so it
// is where the "external form emails are not being sent" warning has to appear — and it
// must appear before the secrets list resolves, since a tenant with no secrets at all is
// exactly the case that needs it.
const h = vi.hoisted(() => ({
  smtpStatus: null as any,
  smtpFails: false,
  statusTenantIds: [] as (string | null | undefined)[],
  isSuperAdmin: false,
  selectedTenantId: null as string | null,
  secretsResponse: { results: [], pagination: { pages: 1, count: 0, total: 0 } } as any,
}));

vi.mock('../services/ExternalFormNotificationService', () => ({
  getSmtpStatus: (tenantId?: string | null) => {
    h.statusTenantIds.push(tenantId);
    return h.smtpFails
      ? Promise.reject(new Error('403'))
      : Promise.resolve(h.smtpStatus);
  },
  clearSmtpStatusCache: () => {},
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST', DELETE: 'DELETE' },
    makeCallToBackend: vi.fn((opts: any) => {
      if (opts.path.startsWith('/secrets')) {
        opts.successCallback(h.secretsResponse);
      }
    }),
  },
}));

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: () => ({
    ability: { can: () => true },
    permissionsLoaded: true,
  }),
}));

vi.mock('../hooks/UriListForPermissions', () => ({
  useUriListForPermissions: () => ({
    targetUris: { secretListPath: '/secrets', authenticationListPath: '/authentications' },
  }),
}));

vi.mock('../services/UserService', () => ({
  default: { isSuperAdmin: () => h.isSuperAdmin },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: () => ({ selectedTenantId: h.selectedTenantId }),
}));

vi.mock('../components/PaginationForTable', () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div>{tableToDisplay}</div>
  ),
}));

vi.mock('@casl/react', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('react-i18next', () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

vi.mock('react-icons/md', () => ({ MdDelete: () => <span /> }));

vi.mock('../helpers', () => ({
  getPageInfoFromSearchParams: () => ({ page: 1, perPage: 10 }),
}));

import SecretList from './SecretList';

const renderPage = () =>
  render(
    <MemoryRouter>
      <SecretList />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.smtpStatus = null;
  h.smtpFails = false;
  h.statusTenantIds = [];
  h.isSuperAdmin = false;
  h.selectedTenantId = null;
  h.secretsResponse = { results: [], pagination: { pages: 1, count: 0, total: 0 } };
});

describe('SecretList external form SMTP banner', () => {
  it('warns and names the missing secret keys', async () => {
    h.smtpStatus = {
      configured: false,
      required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      optional_keys: [],
      missing_required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      configured_keys: [],
      fields: [],
    };

    renderPage();

    const banner = await screen.findByTestId('external-form-smtp-not-configured');
    expect(banner.textContent).toContain('NATS_SMTP_HOST');
    expect(banner.textContent).toContain('NATS_SMTP_FROM_EMAIL');
    expect(screen.getByText('external_form_email_configure_action')).toBeInTheDocument();
  });

  it('lists only the keys still missing when some are set', async () => {
    h.smtpStatus = {
      configured: false,
      required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      optional_keys: [],
      missing_required_keys: ['NATS_SMTP_FROM_EMAIL'],
      configured_keys: ['NATS_SMTP_HOST'],
      fields: [],
    };

    renderPage();

    const banner = await screen.findByTestId('external-form-smtp-not-configured');
    expect(banner.textContent).toContain('NATS_SMTP_FROM_EMAIL');
    expect(banner.textContent).not.toContain('NATS_SMTP_HOST');
  });

  it('still shows the required key names once configured, so they stay discoverable', async () => {
    h.smtpStatus = {
      configured: true,
      required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      optional_keys: [],
      missing_required_keys: [],
      configured_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
      fields: [],
    };

    renderPage();

    const banner = await screen.findByTestId('external-form-smtp-configured');
    expect(banner.textContent).toContain('NATS_SMTP_HOST');
    expect(screen.queryByTestId('external-form-smtp-not-configured')).toBeNull();
  });

  it('renders the page normally when the status call fails', async () => {
    h.smtpFails = true;

    renderPage();

    await waitFor(() => expect(screen.getByText('secrets')).toBeInTheDocument());
    expect(screen.queryByTestId('external-form-smtp-not-configured')).toBeNull();
    expect(screen.queryByTestId('external-form-smtp-configured')).toBeNull();
  });

  it('names the tenant for a super admin, whose request is not scoped by the backend', async () => {
    h.isSuperAdmin = true;
    h.selectedTenantId = 'tenant-1';
    h.smtpStatus = {
      configured: true,
      required_keys: ['NATS_SMTP_HOST'],
      optional_keys: [],
      missing_required_keys: [],
      configured_keys: ['NATS_SMTP_HOST'],
      fields: [],
    };

    renderPage();

    await screen.findByTestId('external-form-smtp-configured');
    expect(h.statusTenantIds).toEqual(['tenant-1']);
  });

  it('sends no tenant for an ordinary user, who the backend already scopes', async () => {
    h.isSuperAdmin = false;
    h.selectedTenantId = 'tenant-1';
    h.smtpStatus = {
      configured: true,
      required_keys: ['NATS_SMTP_HOST'],
      optional_keys: [],
      missing_required_keys: [],
      configured_keys: ['NATS_SMTP_HOST'],
      fields: [],
    };

    renderPage();

    await screen.findByTestId('external-form-smtp-configured');
    expect(h.statusTenantIds).toEqual([null]);
  });

  it('says the secret is unreadable rather than missing when it cannot be decrypted', async () => {
    h.smtpStatus = {
      configured: false,
      required_keys: ['NATS_SMTP_HOST'],
      optional_keys: [],
      missing_required_keys: ['NATS_SMTP_HOST'],
      unreadable_keys: ['NATS_SMTP_HOST'],
      reason:
        'SMTP secrets exist but could not be read (blank value, or the backend encryption key changed): NATS_SMTP_HOST',
      configured_keys: [],
      fields: [],
    };

    renderPage();

    const banner = await screen.findByTestId('external-form-smtp-not-configured');
    // Telling an admin to add a key they already added would send them the wrong way.
    expect(banner.textContent).toContain('could not be read');
    expect(banner.textContent).not.toContain('external_form_smtp_missing_hint');
  });
});
