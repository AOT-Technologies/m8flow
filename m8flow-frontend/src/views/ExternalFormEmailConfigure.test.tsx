import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';

const h = vi.hoisted(() => ({
  smtpStatus: null as any,
  notifications: [] as any[],
  resendOk: true,
  cacheCleared: 0,
  statusFetches: 0,
  resendCalls: [] as number[],
  secretCalls: [] as any[],
  secretsPages: {} as Record<string, any>,
  canWriteSecrets: true,
  isSuperAdmin: false,
  selectedTenantId: null as string | null,
  statusTenantIds: [] as (string | null | undefined)[],
  listTenantIds: [] as (string | null | undefined)[],
  clearedTenantIds: [] as (string | null | undefined)[],
  resendTenantIds: [] as (string | null | undefined)[],
}));

vi.mock('../services/ExternalFormNotificationService', () => ({
  getSmtpStatus: (tenantId?: string | null) => {
    h.statusFetches += 1;
    h.statusTenantIds.push(tenantId);
    return Promise.resolve(h.smtpStatus);
  },
  clearSmtpStatusCache: (tenantId?: string | null) => {
    h.cacheCleared += 1;
    h.clearedTenantIds.push(tenantId);
  },
  listNotifications: (params: any = {}) => {
    h.listTenantIds.push(params.tenantId);
    return Promise.resolve({
      results: h.notifications,
      pagination: { count: h.notifications.length, total: h.notifications.length, pages: 1 },
    });
  },
  resendNotification: (id: number, tenantId?: string | null) => {
    h.resendCalls.push(id);
    h.resendTenantIds.push(tenantId);
    return h.resendOk ? Promise.resolve({}) : Promise.reject(new Error('nope'));
  },
}));

vi.mock('../services/UserService', () => ({
  default: { isSuperAdmin: () => h.isSuperAdmin },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: () => ({ selectedTenantId: h.selectedTenantId }),
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST', PUT: 'PUT' },
    makeCallToBackend: vi.fn((opts: any) => {
      h.secretCalls.push(opts);
      if (opts.path.startsWith('/secrets?')) {
        const page = new URLSearchParams(opts.path.split('?')[1]).get('page') ?? '1';
        opts.successCallback(
          h.secretsPages[page] ?? { results: [], pagination: { pages: 1 } },
        );
      } else {
        opts.successCallback({});
      }
    }),
  },
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: () => ({
    ability: { can: (_action: string, uri: string) => (uri === '/secrets' ? h.canWriteSecrets : true) },
    permissionsLoaded: true,
  }),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: () => ({
    targetUris: {
      secretListPath: '/secrets',
      m8flowExternalFormNotificationsPath: '/m8flow/external-form-notifications',
    },
  }),
}));

vi.mock('react-i18next', () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

vi.mock('../components/Notification', () => ({
  Notification: ({ title }: { title?: string }) => (
    <div data-testid="notification">{title}</div>
  ),
}));

vi.mock('../helpers', () => ({ setPageTitle: vi.fn() }));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        // Must NOT return a function for `then` (or symbols) or the mocked
        // module namespace looks like a never-resolving thenable and vitest
        // hangs awaiting it during collection.
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      // vitest validates accessed exports with `prop in module` and throws
      // "No <name> export is defined" otherwise — report every icon as present.
      has: () => true,
    },
  );
});

import ExternalFormEmailConfigure from './ExternalFormEmailConfigure';

const FIELDS = [
  { id: 'host', secretKey: 'NATS_SMTP_HOST', label: 'SMTP Host', type: 'text', required: true },
  {
    id: 'from_email',
    secretKey: 'NATS_SMTP_FROM_EMAIL',
    label: 'From Email',
    type: 'text',
    required: true,
    format: 'email',
  },
];

const renderPage = () =>
  render(
    <MemoryRouter>
      <ExternalFormEmailConfigure />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.smtpStatus = {
    configured: false,
    required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
    optional_keys: [],
    missing_required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
    configured_keys: [],
    fields: FIELDS,
  };
  h.notifications = [];
  h.resendOk = true;
  h.cacheCleared = 0;
  h.statusFetches = 0;
  h.resendCalls = [];
  h.secretCalls = [];
  h.secretsPages = { '1': { results: [], pagination: { pages: 1 } } };
  h.canWriteSecrets = true;
  h.isSuperAdmin = false;
  h.selectedTenantId = null;
  h.statusTenantIds = [];
  h.listTenantIds = [];
  h.clearedTenantIds = [];
  h.resendTenantIds = [];
});

describe('ExternalFormEmailConfigure', () => {
  it('renders a field per backend-declared SMTP secret key', async () => {
    renderPage();

    expect(await screen.findByTestId('connector-config-field-host')).toBeInTheDocument();
    expect(screen.getByTestId('connector-config-field-from_email')).toBeInTheDocument();
    // The key names come from the backend, so they stay discoverable in the UI.
    // They appear both in the missing-secrets banner and under each field.
    expect(screen.getAllByText('NATS_SMTP_HOST').length).toBeGreaterThan(0);
    expect(screen.getAllByText('NATS_SMTP_FROM_EMAIL').length).toBeGreaterThan(0);
  });

  it('warns while required secrets are missing', async () => {
    renderPage();

    expect(await screen.findByTestId('external-form-email-not-configured')).toBeInTheDocument();
  });

  it('confirms once configured', async () => {
    h.smtpStatus = { ...h.smtpStatus, configured: true, missing_required_keys: [] };

    renderPage();

    expect(await screen.findByTestId('external-form-email-configured')).toBeInTheDocument();
  });

  it('saves entered values as secrets and refreshes the cached status', async () => {
    renderPage();
    const host = await screen.findByTestId('connector-config-field-host');

    fireEvent.change(host.querySelector('input')!, { target: { value: 'smtp.example.com' } });
    fireEvent.change(
      screen.getByTestId('connector-config-field-from_email').querySelector('input')!,
      { target: { value: 'no-reply@example.com' } },
    );
    fireEvent.click(screen.getByTestId('connector-config-save'));

    await waitFor(() => expect(h.cacheCleared).toBe(1));
    const posts = h.secretCalls.filter((call) => call.httpMethod === 'POST');
    expect(posts.map((call) => call.postBody.key)).toEqual([
      'NATS_SMTP_HOST',
      'NATS_SMTP_FROM_EMAIL',
    ]);
    // A stale cached status would keep the warning up after a successful save.
    expect(h.statusFetches).toBeGreaterThan(1);
  });

  it('offers Resend only for notifications that never reached the recipient', async () => {
    h.notifications = [
      { id: 1, email: 'a@x.com', status: 'smtp_unconfigured', attempts: 0, last_error: 'Missing required secrets: NATS_SMTP_HOST' },
      { id: 2, email: 'b@x.com', status: 'notified', attempts: 1, last_error: null },
    ];

    renderPage();

    expect(await screen.findByTestId('external-form-notification-resend-1')).toBeInTheDocument();
    expect(screen.queryByTestId('external-form-notification-resend-2')).toBeNull();
    // The stored failure reason is what removes the need to read worker logs.
    const table = screen.getByTestId('external-form-notification-table');
    expect(table.textContent).toContain('Missing required secrets: NATS_SMTP_HOST');
  });

  it('requeues a notification by its numeric id', async () => {
    h.notifications = [
      { id: 7, email: 'a@x.com', status: 'failed', attempts: 2, last_error: 'smtp down' },
    ];

    renderPage();
    fireEvent.click(await screen.findByTestId('external-form-notification-resend-7'));

    await waitFor(() => expect(h.resendCalls).toEqual([7]));
  });

  it('scopes every call to the selected tenant for a super admin', async () => {
    h.isSuperAdmin = true;
    h.selectedTenantId = 'tenant-1';
    h.notifications = [
      { id: 7, email: 'a@x.com', status: 'failed', attempts: 2, last_error: 'smtp down' },
    ];

    renderPage();
    fireEvent.click(await screen.findByTestId('external-form-notification-resend-7'));
    await waitFor(() => expect(h.resendCalls).toEqual([7]));

    expect(h.statusTenantIds.every((id) => id === 'tenant-1')).toBe(true);
    expect(h.listTenantIds.every((id) => id === 'tenant-1')).toBe(true);
    expect(h.resendTenantIds).toEqual(['tenant-1']);
  });

  it('invalidates only the current tenant after saving', async () => {
    h.isSuperAdmin = true;
    h.selectedTenantId = 'tenant-1';

    renderPage();
    const host = await screen.findByTestId('connector-config-field-host');
    fireEvent.change(host.querySelector('input')!, { target: { value: 'smtp.example.com' } });
    fireEvent.change(
      screen.getByTestId('connector-config-field-from_email').querySelector('input')!,
      { target: { value: 'no-reply@example.com' } },
    );
    fireEvent.click(screen.getByTestId('connector-config-save'));

    await waitFor(() => expect(h.clearedTenantIds).toEqual(['tenant-1']));
  });

  it('redirects users without secret write permission', async () => {
    h.canWriteSecrets = false;

    renderPage();

    await waitFor(() =>
      expect(screen.queryByTestId('connector-config-field-host')).toBeNull(),
    );
  });
});
