import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  calls: [] as Array<{ path: string; httpMethod?: string; postBody?: any }>,
  respond: null as null | ((opts: any) => { ok: boolean; value: any }),
}));

vi.mock('./HttpService', () => ({
  default: {
    makeCallToBackend: (opts: any) => {
      h.calls.push({
        path: opts.path,
        httpMethod: opts.httpMethod,
        postBody: opts.postBody,
      });
      const result = h.respond?.(opts) ?? { ok: true, value: {} };
      if (result.ok) {
        opts.successCallback(result.value);
      } else {
        opts.failureCallback(result.value);
      }
    },
  },
}));

import {
  clearSmtpStatusCache,
  getSmtpStatus,
  listNotifications,
  resendNotification,
  SMTP_STATUS_PATH,
} from './ExternalFormNotificationService';

const CONFIGURED = {
  configured: true,
  required_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optional_keys: ['NATS_SMTP_PORT'],
  missing_required_keys: [],
  configured_keys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  fields: [],
};

beforeEach(() => {
  h.calls = [];
  h.respond = () => ({ ok: true, value: CONFIGURED });
  clearSmtpStatusCache();
});

describe('getSmtpStatus caching', () => {
  it('issues one request for concurrent and repeat callers', async () => {
    const [a, b] = await Promise.all([getSmtpStatus(), getSmtpStatus()]);
    const c = await getSmtpStatus();

    expect(a).toEqual(CONFIGURED);
    expect(b).toEqual(CONFIGURED);
    expect(c).toEqual(CONFIGURED);
    expect(h.calls.filter((call) => call.path === SMTP_STATUS_PATH)).toHaveLength(1);
  });

  it('refetches after the cache is cleared', async () => {
    await getSmtpStatus();
    clearSmtpStatusCache();
    await getSmtpStatus();

    expect(h.calls.filter((call) => call.path === SMTP_STATUS_PATH)).toHaveLength(2);
  });

  it('caches per tenant so a switch does not reuse the previous verdict', async () => {
    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');
    await getSmtpStatus('tenant-1');

    const paths = h.calls.map((call) => call.path);
    expect(paths).toEqual([
      `${SMTP_STATUS_PATH}?tenantId=tenant-1`,
      `${SMTP_STATUS_PATH}?tenantId=tenant-2`,
    ]);
  });

  it('clears only the named tenant', async () => {
    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');
    clearSmtpStatusCache('tenant-1');
    await getSmtpStatus('tenant-1');
    await getSmtpStatus('tenant-2');

    expect(h.calls.filter((c) => c.path.includes('tenant-1'))).toHaveLength(2);
    expect(h.calls.filter((c) => c.path.includes('tenant-2'))).toHaveLength(1);
  });

  it('does not send a tenantId when none is given', async () => {
    await getSmtpStatus(null);

    expect(h.calls[0].path).toBe(SMTP_STATUS_PATH);
  });

  it('does not cache a failure', async () => {
    h.respond = () => ({ ok: false, value: new Error('403') });
    await expect(getSmtpStatus()).rejects.toBeTruthy();

    // A 403 for one render, or a transient error, must not poison the session.
    h.respond = () => ({ ok: true, value: CONFIGURED });
    await expect(getSmtpStatus()).resolves.toEqual(CONFIGURED);
    expect(h.calls.filter((call) => call.path === SMTP_STATUS_PATH)).toHaveLength(2);
  });
});

describe('listNotifications', () => {
  it('sends pagination and filter params', async () => {
    h.respond = () => ({ ok: true, value: { results: [], pagination: {} } });

    await listNotifications({ page: 2, perPage: 5, status: 'smtp_unconfigured', processInstanceId: 42 });

    const { path } = h.calls[0];
    expect(path).toContain('/m8flow/external-form-notifications?');
    expect(path).toContain('page=2');
    expect(path).toContain('per_page=5');
    expect(path).toContain('status=smtp_unconfigured');
    expect(path).toContain('process_instance_id=42');
  });

  it('omits filters that were not supplied', async () => {
    h.respond = () => ({ ok: true, value: { results: [], pagination: {} } });

    await listNotifications();

    const { path } = h.calls[0];
    expect(path).not.toContain('status=');
    expect(path).not.toContain('process_instance_id=');
    expect(path).not.toContain('tenantId=');
  });

  it('passes the tenant so a super admin is not shown every tenant', async () => {
    h.respond = () => ({ ok: true, value: { results: [], pagination: {} } });

    await listNotifications({ tenantId: 'tenant-1' });

    expect(h.calls[0].path).toContain('tenantId=tenant-1');
  });
});

describe('resendNotification', () => {
  it('POSTs to the resend route for the numeric id', async () => {
    h.respond = () => ({ ok: true, value: { ok: true } });

    await resendNotification(7);

    expect(h.calls[0]).toMatchObject({
      path: '/m8flow/external-form-notifications/7/resend',
      httpMethod: 'POST',
    });
  });

  it('scopes the resend to a tenant when one is given', async () => {
    h.respond = () => ({ ok: true, value: { ok: true } });

    await resendNotification(7, 'tenant-1');

    expect(h.calls[0].path).toBe(
      '/m8flow/external-form-notifications/7/resend?tenantId=tenant-1',
    );
  });
});
