import { describe, it, expect, vi, beforeEach } from 'vitest';

const makeCallToBackend = vi.hoisted(() => vi.fn());

vi.mock('@spiffworkflow-frontend/services/HttpService', () => ({
  default: { makeCallToBackend },
}));

import {
  clearSmtpStatusCache,
  getNotifications,
  getSmtpStatus,
  resendNotification,
} from './ExternalFormNotificationService';

const CONFIGURED = {
  configured: true,
  required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optional_keys: ['NATS_SMTP_PORT'],
  missing_required_keys: [],
  unreadable_keys: [],
  reason: null,
  configured_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
};

function respondWith(payload: any) {
  makeCallToBackend.mockImplementation((opts: any) => {
    opts.successCallback(payload);
  });
}

function failWith(error: any) {
  makeCallToBackend.mockImplementation((opts: any) => {
    opts.failureCallback(error);
  });
}

beforeEach(() => {
  makeCallToBackend.mockReset();
  clearSmtpStatusCache();
});

describe('getSmtpStatus', () => {
  it('requests the status path without a /v1.0 prefix duplication', async () => {
    respondWith(CONFIGURED);

    await getSmtpStatus();

    expect(makeCallToBackend).toHaveBeenCalledTimes(1);
    expect(makeCallToBackend.mock.calls[0][0].path).toBe(
      '/v1.0/m8flow/external-form-notifications/smtp-status',
    );
    expect(makeCallToBackend.mock.calls[0][0].httpMethod).toBe('GET');
  });

  it('passes the tenant id through for super admins', async () => {
    respondWith(CONFIGURED);

    await getSmtpStatus('tenant-1');

    expect(makeCallToBackend.mock.calls[0][0].path).toBe(
      '/v1.0/m8flow/external-form-notifications/smtp-status?tenantId=tenant-1',
    );
  });

  it('shares one in-flight request between concurrent callers', async () => {
    respondWith(CONFIGURED);

    const [a, b] = await Promise.all([getSmtpStatus(), getSmtpStatus()]);

    expect(makeCallToBackend).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
  });

  it('caches per tenant so switching tenants re-fetches', async () => {
    respondWith(CONFIGURED);

    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');
    await getSmtpStatus('tenant-1');

    // One call per distinct tenant; the repeat is served from the cache. A single
    // unkeyed entry would report tenant-1's verdict for tenant-2.
    expect(makeCallToBackend).toHaveBeenCalledTimes(2);
    const paths = makeCallToBackend.mock.calls.map((call: any) => call[0].path);
    expect(paths[0]).toContain('tenantId=tenant-1');
    expect(paths[1]).toContain('tenantId=tenant-2');
  });

  it('does not cache a failure, so a later retry still reaches the backend', async () => {
    failWith(new Error('403'));
    await expect(getSmtpStatus()).rejects.toBeTruthy();

    respondWith(CONFIGURED);
    await expect(getSmtpStatus()).resolves.toEqual(CONFIGURED);

    expect(makeCallToBackend).toHaveBeenCalledTimes(2);
  });

  it('clearSmtpStatusCache forces a refetch for one tenant', async () => {
    respondWith(CONFIGURED);
    await getSmtpStatus('tenant-1');

    clearSmtpStatusCache('tenant-1');
    await getSmtpStatus('tenant-1');

    expect(makeCallToBackend).toHaveBeenCalledTimes(2);
  });

  it('clearSmtpStatusCache with no arguments clears all cached tenants', async () => {
    respondWith(CONFIGURED);
    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');
    expect(makeCallToBackend).toHaveBeenCalledTimes(2);

    clearSmtpStatusCache();
    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');

    expect(makeCallToBackend).toHaveBeenCalledTimes(4);
  });

  it('getSmtpStatus with force: true bypasses and replaces the cached verdict', async () => {
    respondWith(CONFIGURED);
    await getSmtpStatus('tenant-1');
    expect(makeCallToBackend).toHaveBeenCalledTimes(1);

    await getSmtpStatus('tenant-1', { force: true });
    expect(makeCallToBackend).toHaveBeenCalledTimes(2);

    // Subsequent regular call uses the new cached entry
    await getSmtpStatus('tenant-1');
    expect(makeCallToBackend).toHaveBeenCalledTimes(2);
  });

  it('surfaces the missing key names when the tenant is unconfigured', async () => {
    respondWith({
      ...CONFIGURED,
      configured: false,
      missing_required_keys: ['NATS_SMTP_HOST'],
      configured_keys: ['NATS_SMTP_FROM_EMAIL'],
      reason: 'SMTP is not configured for this tenant.',
    });

    const status = await getSmtpStatus();

    expect(status.configured).toBe(false);
    expect(status.missing_required_keys).toEqual(['NATS_SMTP_HOST']);
  });
});

describe('getNotifications', () => {
  it('requests the bare collection path with no query when unfiltered', async () => {
    respondWith({ results: [], pagination: { count: 0, total: 0, pages: 0 } });

    await getNotifications();

    expect(makeCallToBackend.mock.calls[0][0].path).toBe(
      '/v1.0/m8flow/external-form-notifications',
    );
  });

  it('serializes every supported filter', async () => {
    respondWith({ results: [], pagination: { count: 0, total: 0, pages: 0 } });

    await getNotifications({
      processInstanceId: 42,
      status: 'smtp_unconfigured',
      page: 2,
      perPage: 25,
      tenantId: 'tenant-1',
    });

    const { path } = makeCallToBackend.mock.calls[0][0];
    expect(path).toContain('process_instance_id=42');
    expect(path).toContain('status=smtp_unconfigured');
    expect(path).toContain('page=2');
    expect(path).toContain('per_page=25');
    expect(path).toContain('tenantId=tenant-1');
  });

  it('returns the parsed page', async () => {
    const page = {
      results: [{ id: 1, status: 'smtp_unconfigured', last_error: 'no smtp' }],
      pagination: { count: 1, total: 1, pages: 1 },
    };
    respondWith(page);

    await expect(getNotifications()).resolves.toEqual(page);
  });
});

describe('resendNotification', () => {
  it('POSTs to the resend path', async () => {
    respondWith({ ok: true, id: 7, status: 'pending', message: 'queued' });

    await resendNotification(7);

    const call = makeCallToBackend.mock.calls[0][0];
    expect(call.path).toBe(
      '/v1.0/m8flow/external-form-notifications/7/resend',
    );
    expect(call.httpMethod).toBe('POST');
  });

  it('includes the tenant id when given', async () => {
    respondWith({ ok: true, id: 7, status: 'pending', message: 'queued' });

    await resendNotification(7, 'tenant-1');

    expect(makeCallToBackend.mock.calls[0][0].path).toBe(
      '/v1.0/m8flow/external-form-notifications/7/resend?tenantId=tenant-1',
    );
  });

  it('rejects when the row cannot be resent', async () => {
    failWith({ error_code: 'external_form_request_not_resendable' });

    await expect(resendNotification(7)).rejects.toEqual({
      error_code: 'external_form_request_not_resendable',
    });
  });
});
