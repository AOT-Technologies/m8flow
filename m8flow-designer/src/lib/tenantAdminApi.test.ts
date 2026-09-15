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

describe('tenantAdminApi helpers', () => {
  it('normalizes and validates group names against the API rules', async () => {
    const {
      normalizeTenantGroupName,
      validateTenantGroupName,
      TENANT_GROUP_NAME_MAX_LENGTH,
    } = await import('./tenantAdminApi');
    expect(normalizeTenantGroupName('  QA   Reviewers  ')).toBe('QA Reviewers');
    expect(validateTenantGroupName('')).toBe('Group name cannot be empty');
    expect(validateTenantGroupName('a'.repeat(TENANT_GROUP_NAME_MAX_LENGTH + 1))).toContain(
      String(TENANT_GROUP_NAME_MAX_LENGTH),
    );
    expect(validateTenantGroupName('-leading')).toContain('start and end');
    expect(validateTenantGroupName('QA Reviewers')).toBeNull();
    expect(validateTenantGroupName('editors_1')).toBeNull();
  });
});

describe('tenantAdminApi', () => {
  beforeEach(() => {
    vi.resetModules();
    getAccessToken.mockReset().mockReturnValue('access-token');
    resumeLoginAfterLogout.mockReset();
    vi.unstubAllGlobals();
  });

  it('lists members with search, offset, and limit', async () => {
    const { fetchTenantMembers } = await import('./tenantAdminApi');
    const body = {
      tenant_id: 't1',
      search: 'ed',
      offset: 10,
      limit: 5,
      has_more: true,
      members: [{ id: 'u1', username: 'editor', roles: ['editor'], groups: [] }],
    };
    const fetchMock = vi.fn().mockResolvedValue(makeResponse({ ok: true, status: 200, body }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchTenantMembers('t1', { search: 'ed', offset: 10, limit: 5 });
    expect(result).toEqual(body);
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/members?');
    expect(firstUrl(fetchMock)).toContain('search=ed');
    expect(firstUrl(fetchMock)).toContain('offset=10');
    expect(firstUrl(fetchMock)).toContain('limit=5');
  });

  it('lists available users for Add Member', async () => {
    const { fetchAvailableTenantUsers } = await import('./tenantAdminApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: { tenant_id: 't1', search: '', offset: 0, limit: 10, has_more: false, users: [] },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchAvailableTenantUsers('acme/prod');
    expect(firstUrl(fetchMock)).toContain(
      `/v1.0/m8flow/tenants/${encodeURIComponent('acme/prod')}/available-users`,
    );
  });

  it('adds an existing user with optional group names', async () => {
    const { addTenantMember } = await import('./tenantAdminApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 201,
        body: {
          tenant_id: 't1',
          group_names: ['editors'],
          member: { id: 'u1', username: 'editor', roles: [], groups: [] },
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await addTenantMember('t1', { username: 'editor', group_names: ['editors'] });
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(String(firstInit(fetchMock).body))).toEqual({
      username: 'editor',
      group_names: ['editors'],
    });
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/members');
    expect(firstUrl(fetchMock)).not.toContain('/members/editor');
  });

  it('removes a member by username', async () => {
    const { removeTenantMember } = await import('./tenantAdminApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({ ok: true, status: 200, body: { tenant_id: 't1', username: 'editor' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await removeTenantMember('t1', 'editor@org');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'DELETE' }));
    expect(firstUrl(fetchMock)).toContain(
      `/v1.0/m8flow/tenants/t1/members/${encodeURIComponent('editor@org')}`,
    );
  });

  it('adds and removes group membership without calling member-role routes', async () => {
    const { addTenantGroupMember, removeTenantGroupMember } = await import('./tenantAdminApi');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', group_name: 'editors', username: 'editor', member: { username: 'editor' } },
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', group_name: 'editors', username: 'editor', member: { username: 'editor' } },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await addTenantGroupMember('t1', 'editors', 'editor');
    await removeTenantGroupMember('t1', 'editors', 'editor');

    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'PUT' }));
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: 'DELETE' }));
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      '/v1.0/m8flow/tenants/t1/groups/editors/members/editor',
    );
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      '/v1.0/m8flow/tenants/t1/groups/editors/members/editor',
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/members/editor/roles/');
  });

  it('lists, creates, renames, and deletes groups', async () => {
    const { fetchTenantGroups, createTenantGroup, renameTenantGroup, deleteTenantGroup } =
      await import('./tenantAdminApi');
    const group = {
      id: 'g1',
      name: 'editors',
      path: '/editors',
      mapped_roles: ['editor'],
      member_count: 1,
      members: [],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', search: '', offset: 0, limit: 10, has_more: false, groups: [group] },
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({ ok: true, status: 201, body: { tenant_id: 't1', group } }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', previous_group_name: 'editors', group: { ...group, name: 'reviewers' } },
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({ ok: true, status: 200, body: { tenant_id: 't1', group_name: 'reviewers' } }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const listed = await fetchTenantGroups('t1');
    expect(listed.groups).toHaveLength(1);
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/groups');

    await createTenantGroup('t1', 'editors');
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({ name: 'editors' });

    await renameTenantGroup('t1', 'editors', 'reviewers');
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({ method: 'PUT' }));
    expect(JSON.parse(String(fetchMock.mock.calls[2][1].body))).toEqual({ name: 'reviewers' });

    await deleteTenantGroup('t1', 'qa team');
    expect(fetchMock.mock.calls[3][1]).toEqual(expect.objectContaining({ method: 'DELETE' }));
    expect(String(fetchMock.mock.calls[3][0])).toContain(
      `/v1.0/m8flow/tenants/t1/groups/${encodeURIComponent('qa team')}`,
    );
  });

  it('grants and revokes the six tenant roles on a group', async () => {
    const { TENANT_ROLES, grantTenantGroupRole, revokeTenantGroupRole } = await import('./tenantAdminApi');
    expect(TENANT_ROLES).toEqual([
      'tenant-admin',
      'editor',
      'integrator',
      'reviewer',
      'submitter',
      'viewer',
    ]);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', group_name: 'editors', role_name: 'submitter', group: { name: 'editors' } },
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          ok: true,
          status: 200,
          body: { tenant_id: 't1', group_name: 'editors', role_name: 'submitter', group: { name: 'editors' } },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await grantTenantGroupRole('t1', 'editors', 'submitter');
    await revokeTenantGroupRole('t1', 'editors', 'submitter');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'PUT' }));
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: 'DELETE' }));
    expect(firstUrl(fetchMock)).toContain('/v1.0/m8flow/tenants/t1/groups/editors/roles/submitter');
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      '/v1.0/m8flow/tenants/t1/groups/editors/roles/submitter',
    );
  });

  it('surfaces backend detail on member conflict', async () => {
    const { addTenantMember, tenantAdminErrorMessage } = await import('./tenantAdminApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: false,
        status: 409,
        body: { message: 'User is already a member of this tenant.' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(addTenantMember('t1', { username: 'editor' })).rejects.toMatchObject({
      status: 409,
      serverMessage: 'User is already a member of this tenant.',
    });
    const { ApiError } = await import('./api');
    expect(
      tenantAdminErrorMessage(
        new ApiError('/x', 409, 'POST', 'User is already a member of this tenant.'),
        'fallback',
      ),
    ).toBe('User is already a member of this tenant.');
  });
});
