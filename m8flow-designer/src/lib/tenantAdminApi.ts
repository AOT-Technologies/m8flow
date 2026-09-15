import { apiFetch, apiGet, ApiError } from './api';

export const TENANT_ROLES = [
  'tenant-admin',
  'editor',
  'integrator',
  'reviewer',
  'submitter',
  'viewer',
] as const;

export type TenantRole = (typeof TENANT_ROLES)[number];

export const TENANT_GROUP_NAME_MAX_LENGTH = 64;
const TENANT_GROUP_NAME_ALLOWED = /^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$/;

export function normalizeTenantGroupName(name: string): string {
  return name.trim().replace(/\s+/g, ' ');
}

export function validateTenantGroupName(name: string): string | null {
  const normalized = normalizeTenantGroupName(name);
  if (!normalized) {
    return 'Group name cannot be empty';
  }
  if (normalized.length > TENANT_GROUP_NAME_MAX_LENGTH) {
    return `Group name must be ${TENANT_GROUP_NAME_MAX_LENGTH} characters or fewer`;
  }
  if (!TENANT_GROUP_NAME_ALLOWED.test(normalized)) {
    return 'Group name can only contain letters, numbers, spaces, hyphens, and underscores, and must start and end with a letter or number';
  }
  return null;
}

export type TenantMemberGroup = {
  id: string;
  name: string;
};

export type TenantMember = {
  id: string;
  username: string;
  email?: string | null;
  display_name?: string | null;
  roles: TenantRole[];
  groups: TenantMemberGroup[];
};

export type TenantMemberList = {
  tenant_id: string;
  search: string;
  offset: number;
  limit: number;
  has_more: boolean;
  members: TenantMember[];
};

export type TenantAvailableUser = {
  id: string;
  username: string;
  email?: string | null;
  display_name?: string | null;
};

export type TenantAvailableUserList = {
  tenant_id: string;
  search: string;
  offset: number;
  limit: number;
  has_more: boolean;
  users: TenantAvailableUser[];
};

export type TenantMemberCreateResponse = {
  tenant_id: string;
  group_names: string[];
  member: TenantMember;
};

export type TenantGroupMember = TenantAvailableUser;

export type TenantGroup = {
  id: string;
  name: string;
  path?: string | null;
  mapped_roles: TenantRole[];
  member_count: number;
  members: TenantGroupMember[];
};

export type TenantGroupList = {
  tenant_id: string;
  search: string;
  offset: number;
  limit: number;
  has_more: boolean;
  groups: TenantGroup[];
};

export type TenantGroupMutationResponse = {
  tenant_id: string;
  group: TenantGroup;
};

export type TenantGroupMembershipMutationResponse = {
  tenant_id: string;
  group_name: string;
  username: string;
  member: TenantMember;
};

export type TenantGroupRoleMutationResponse = {
  tenant_id: string;
  group_name: string;
  role_name: TenantRole;
  group: TenantGroup;
};

type PageQuery = {
  search?: string;
  offset?: number;
  limit?: number;
};

function tenantPath(tenantId: string, suffix: string): string {
  return `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}${suffix}`;
}

function withQuery(path: string, query: PageQuery = {}): string {
  const params = new URLSearchParams();
  if (query.search) {
    params.set('search', query.search);
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset));
  }
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

async function jsonFetch<T>(path: string, init: RequestInit): Promise<T> {
  const response = await apiFetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init.headers },
  });
  return (await response.json()) as T;
}

export function tenantAdminErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.serverMessage) {
    return error.serverMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function fetchTenantMembers(
  tenantId: string,
  query: PageQuery = {},
): Promise<TenantMemberList> {
  return apiGet<TenantMemberList>(withQuery(tenantPath(tenantId, '/members'), query));
}

export function fetchAvailableTenantUsers(
  tenantId: string,
  query: PageQuery = {},
): Promise<TenantAvailableUserList> {
  return apiGet<TenantAvailableUserList>(
    withQuery(tenantPath(tenantId, '/available-users'), query),
  );
}

export function addTenantMember(
  tenantId: string,
  payload: { username: string; group_names?: string[] },
): Promise<TenantMemberCreateResponse> {
  const body: { username: string; group_names?: string[] } = { username: payload.username };
  if (payload.group_names) {
    body.group_names = payload.group_names;
  }
  return jsonFetch<TenantMemberCreateResponse>(tenantPath(tenantId, '/members'), {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function removeTenantMember(tenantId: string, username: string): Promise<void> {
  await apiFetch(
    tenantPath(tenantId, `/members/${encodeURIComponent(username)}`),
    { method: 'DELETE' },
  );
}

export function addTenantGroupMember(
  tenantId: string,
  groupName: string,
  username: string,
): Promise<TenantGroupMembershipMutationResponse> {
  return jsonFetch<TenantGroupMembershipMutationResponse>(
    tenantPath(
      tenantId,
      `/groups/${encodeURIComponent(groupName)}/members/${encodeURIComponent(username)}`,
    ),
    { method: 'PUT' },
  );
}

export function removeTenantGroupMember(
  tenantId: string,
  groupName: string,
  username: string,
): Promise<TenantGroupMembershipMutationResponse> {
  return jsonFetch<TenantGroupMembershipMutationResponse>(
    tenantPath(
      tenantId,
      `/groups/${encodeURIComponent(groupName)}/members/${encodeURIComponent(username)}`,
    ),
    { method: 'DELETE' },
  );
}

export function fetchTenantGroups(
  tenantId: string,
  query: PageQuery = {},
): Promise<TenantGroupList> {
  return apiGet<TenantGroupList>(withQuery(tenantPath(tenantId, '/groups'), query));
}

export function createTenantGroup(
  tenantId: string,
  name: string,
): Promise<TenantGroupMutationResponse> {
  return jsonFetch<TenantGroupMutationResponse>(tenantPath(tenantId, '/groups'), {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function renameTenantGroup(
  tenantId: string,
  groupName: string,
  name: string,
): Promise<TenantGroupMutationResponse & { previous_group_name: string }> {
  return jsonFetch<TenantGroupMutationResponse & { previous_group_name: string }>(
    tenantPath(tenantId, `/groups/${encodeURIComponent(groupName)}`),
    {
      method: 'PUT',
      body: JSON.stringify({ name }),
    },
  );
}

export async function deleteTenantGroup(tenantId: string, groupName: string): Promise<void> {
  await apiFetch(tenantPath(tenantId, `/groups/${encodeURIComponent(groupName)}`), {
    method: 'DELETE',
  });
}

export function grantTenantGroupRole(
  tenantId: string,
  groupName: string,
  roleName: TenantRole,
): Promise<TenantGroupRoleMutationResponse> {
  return jsonFetch<TenantGroupRoleMutationResponse>(
    tenantPath(
      tenantId,
      `/groups/${encodeURIComponent(groupName)}/roles/${encodeURIComponent(roleName)}`,
    ),
    { method: 'PUT' },
  );
}

export function revokeTenantGroupRole(
  tenantId: string,
  groupName: string,
  roleName: TenantRole,
): Promise<TenantGroupRoleMutationResponse> {
  return jsonFetch<TenantGroupRoleMutationResponse>(
    tenantPath(
      tenantId,
      `/groups/${encodeURIComponent(groupName)}/roles/${encodeURIComponent(roleName)}`,
    ),
    { method: 'DELETE' },
  );
}
