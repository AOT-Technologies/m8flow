import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getAccessToken, resumeLoginAfterLogout } = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  resumeLoginAfterLogout: vi.fn(),
}));

vi.mock('./auth', () => ({
  getAccessToken,
  resumeLoginAfterLogout,
}));

const makeResponse = ({
  ok,
  status,
  body,
}: {
  ok: boolean;
  status: number;
  body?: unknown;
}) => ({
  ok,
  status,
  statusText: ok ? 'OK' : 'Error',
  json: vi.fn().mockResolvedValue(body ?? {}),
  clone: vi.fn().mockReturnThis(),
  text: vi.fn().mockResolvedValue(JSON.stringify(body ?? {})),
});

function firstUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls[0][0]);
}

function firstInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

describe('invitationManagementApi', () => {
  beforeEach(() => {
    vi.resetModules();
    getAccessToken.mockReset().mockReturnValue('access-token');
    resumeLoginAfterLogout.mockReset();
    vi.unstubAllGlobals();
  });

  it('lists invitations with optional status, offset, and limit', async () => {
    const { fetchTenantInvitations } = await import('./invitationManagementApi');
    const body = {
      tenant_id: 't1',
      results: [{ id: 'inv1', email: 'a@example.com', status: 'PENDING', roles: ['editor'] }],
      total: 1,
      offset: 0,
      limit: 10,
    };
    const fetchMock = vi.fn().mockResolvedValue(makeResponse({ ok: true, status: 200, body }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchTenantInvitations('t1', { status: 'PENDING', offset: 0, limit: 10 });
    expect(result).toEqual(body);
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/invitations?');
    expect(firstUrl(fetchMock)).toContain('status=PENDING');
    expect(firstUrl(fetchMock)).toContain('offset=0');
    expect(firstUrl(fetchMock)).toContain('limit=10');
    expect(firstUrl(fetchMock)).not.toContain('/invitations/validate');
    expect(firstUrl(fetchMock)).not.toContain('/invitations/accept');
  });

  it('creates an invitation with email, roles, and optional validity_days', async () => {
    const { createTenantInvitation } = await import('./invitationManagementApi');
    const invitation = {
      id: 'inv1',
      tenant_id: 't1',
      email: 'a@example.com',
      roles: ['editor', 'submitter'],
      status: 'PENDING',
      invitation_link: 'http://localhost/accept?token=x',
    };
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({ ok: true, status: 201, body: { tenant_id: 't1', invitation } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const created = await createTenantInvitation('t1', {
      email: 'a@example.com',
      roles: ['editor', 'submitter'],
      validity_days: 7,
    });
    expect(created.invitation).toEqual(invitation);
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(String(firstInit(fetchMock).body))).toEqual({
      email: 'a@example.com',
      roles: ['editor', 'submitter'],
      validity_days: 7,
    });
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/invitations');
  });

  it('resends and revokes by invitation id', async () => {
    const { resendTenantInvitation, revokeTenantInvitation } = await import(
      './invitationManagementApi'
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', invitation: { id: 'inv1', status: 'PENDING' } },
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', invitation: { id: 'inv1', status: 'REVOKED' } },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await resendTenantInvitation('t1', 'inv1');
    await revokeTenantInvitation('t1', 'inv1');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'POST' }));
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/invitations/inv1/resend');
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: 'DELETE' }));
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      '/v1.0/m8flow/tenants/t1/invitations/inv1',
    );
  });

  it('prefers ApiError.serverMessage for display', async () => {
    const { invitationManagementErrorMessage } = await import('./invitationManagementApi');
    const { ApiError } = await import('./api');
    const error = new ApiError('/x', 403, 'GET', 'Only super admins can manage tenant invitations.');
    expect(invitationManagementErrorMessage(error, 'fallback')).toBe(
      'Only super admins can manage tenant invitations.',
    );
  });
});
