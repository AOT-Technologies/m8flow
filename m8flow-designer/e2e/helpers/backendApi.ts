import { expect, type Page } from '@playwright/test';

import { cookieValue, masterBootstrapAdminCredentials, SELECTED_TENANT_COOKIE } from './auth';
import {
  KEYCLOAK_BASE_URL,
  MOCK_EMAIL_DOMAIN,
  PARITY_SECOND_TENANT_NAME,
  PARITY_SECOND_TENANT_SLUG,
  SEED_TENANT_SLUG,
  SHARED_REALM,
} from './fixtures';

export type TenantRecord = {
  id: string;
  name: string;
  slug: string;
};

export type InvitationRecord = {
  id: string;
  email: string;
  invitation_link?: string;
};

const INVITE_PASSWORD = 'Parity-e2e-pass-1';

export function uniqueEmail(prefix: string): string {
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return `${prefix}-${stamp}@${MOCK_EMAIL_DOMAIN}`;
}

export function invitationPassword(): string {
  return INVITE_PASSWORD;
}

export function tokenFromInvitationLink(link: string): string {
  const url = new URL(link);
  const token = url.searchParams.get('token');
  if (!token) {
    throw new Error(`invitation_link is missing a token query: ${link}`);
  }
  return token;
}

function assertInvitationLinkHitsDesigner(link: string): void {
  let parsed: URL;
  try {
    parsed = new URL(link);
  } catch {
    throw new Error(`invitation_link is not a URL: ${link}`);
  }
  if (parsed.pathname !== '/accept-invitation') {
    throw new Error(`invitation_link path must be /accept-invitation: ${link}`);
  }
  if (parsed.port === '6841' || parsed.port === '6842') {
    throw new Error(
      `invitation_link must point at m8flow-designer, not leftover frontend or Keycloak: ${link}`,
    );
  }
}

async function parseJson(response: { status: () => number; text: () => Promise<string> }): Promise<unknown> {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`Non-JSON response (${response.status()}): ${text}`);
  }
}

export async function backendFetch(
  page: Page,
  path: string,
  init?: { method?: string; data?: unknown },
): Promise<{ status: number; body: unknown }> {
  const accessToken = await cookieValue(page, 'access_token');
  // Relative /v1.0 paths go through the designer Vite proxy (same origin as
  // the page) so the browser cookie jar is sent. Direct :6840 calls drop
  // those cookies.
  const response = await page.request.fetch(path, {
    method: init?.method ?? 'GET',
    ...(init?.data !== undefined ? { data: init.data } : {}),
    headers: {
      Accept: 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init?.data !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  return { status: response.status(), body: await parseJson(response) };
}

export async function expectOnboardingAndTasks(
  page: Page,
  expected: { username: string },
): Promise<void> {
  const selected = await cookieValue(page, SELECTED_TENANT_COOKIE);
  expect(selected, 'm8flow_selected_tenant must be set after tenant finalization').toBeTruthy();

  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  const accessToken = await cookieValue(page, 'access_token');
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const onboarding = await page.request.get('/v1.0/onboarding', { headers });
  expect(onboarding.status(), await onboarding.text()).toBe(200);
  const payload = (await onboarding.json()) as {
    ok?: boolean;
    username?: string;
    tenant_id?: string;
  };
  expect(payload.ok).toBe(true);
  expect(payload.username).toBe(expected.username);
  expect(payload.tenant_id).toBeTruthy();

  const tasks = await page.request.get('/v1.0/tasks', { headers });
  expect(tasks.status(), await tasks.text()).toBe(200);
  expect(Array.isArray(await tasks.json())).toBe(true);
}

export async function getTenantBySlug(page: Page, slug: string): Promise<TenantRecord> {
  const result = await backendFetch(page, `/v1.0/m8flow/tenants/slug/${encodeURIComponent(slug)}`);
  if (result.status !== 200 || !result.body || typeof result.body !== 'object') {
    throw new Error(`getTenantBySlug(${slug}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  const tenant = result.body as TenantRecord;
  if (!tenant.id) {
    throw new Error(`getTenantBySlug(${slug}) returned no id`);
  }
  return tenant;
}

/**
 * The second test tenant that the baseline seed creates (seed/seed.ts). Tests
 * look it up instead of creating it; a missing tenant means the seed did not
 * finish, so the error says so.
 */
export async function getSeededSecondTenant(page: Page): Promise<TenantRecord> {
  try {
    return await getTenantBySlug(page, PARITY_SECOND_TENANT_SLUG);
  } catch (error) {
    throw new Error(
      `The second test tenant "${PARITY_SECOND_TENANT_SLUG}" was not found: the baseline seed (seed/seed.ts) ` +
        `did not create it. Check the [seed] lines at the start of the run. ${String(error).slice(0, 200)}`,
    );
  }
}

export async function ensureSecondParityTenant(page: Page): Promise<TenantRecord> {
  const existing = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/slug/${encodeURIComponent(PARITY_SECOND_TENANT_SLUG)}`,
  );
  if (existing.status === 200 && existing.body && typeof existing.body === 'object') {
    return existing.body as TenantRecord;
  }

  const created = await backendFetch(page, '/v1.0/m8flow/tenant-realms', {
    method: 'POST',
    data: { slug: PARITY_SECOND_TENANT_SLUG, name: PARITY_SECOND_TENANT_NAME },
  });
  if (created.status === 201 && created.body && typeof created.body === 'object') {
    const body = created.body as { id: string; alias: string; name: string };
    return { id: body.id, slug: body.alias, name: body.name };
  }
  if (created.status === 409) {
    return getTenantBySlug(page, PARITY_SECOND_TENANT_SLUG);
  }
  throw new Error(`ensureSecondParityTenant failed: ${created.status} ${JSON.stringify(created.body)}`);
}

export async function createTenantInvitation(
  page: Page,
  tenantId: string,
  email: string,
  roles: string[] = ['editor'],
): Promise<InvitationRecord> {
  const result = await backendFetch(page, `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/invitations`, {
    method: 'POST',
    data: { email, roles },
  });
  if (result.status !== 201 || !result.body || typeof result.body !== 'object') {
    throw new Error(`createTenantInvitation failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  const wrapper = result.body as { invitation?: InvitationRecord };
  const invitation = wrapper.invitation;
  if (!invitation?.invitation_link) {
    throw new Error(
      'Invitation create did not return invitation_link. Local SMTP must be unset so the accept token is in the JSON.',
    );
  }
  assertInvitationLinkHitsDesigner(invitation.invitation_link);
  return invitation;
}

export async function acceptInvitationApi(page: Page, token: string, password: string): Promise<void> {
  const response = await page.request.post('/v1.0/m8flow/invitations/accept', {
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    data: { token, password },
  });
  if (!response.ok()) {
    throw new Error(`acceptInvitationApi failed: ${response.status()} ${await response.text()}`);
  }
}

export async function addTenantMember(
  page: Page,
  tenantId: string,
  username: string,
  groupNames: string[] = ['Designers'],
): Promise<void> {
  const result = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/members`,
    {
      method: 'POST',
      data: { username, group_names: groupNames },
    },
  );
  if (result.status !== 201 && result.status !== 409) {
    throw new Error(`addTenantMember failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/** True when the shared realm has a user with exactly this user name (Keycloak admin API). */
export async function keycloakUserExists(page: Page, username: string): Promise<boolean> {
  const token = await keycloakAdminToken(page);
  const found = await page.request.get(
    `${KEYCLOAK_BASE_URL}/admin/realms/${encodeURIComponent(SHARED_REALM)}/users?username=${encodeURIComponent(username)}&exact=true`,
    { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' } },
  );
  if (!found.ok()) throw new Error(`Keycloak user lookup for ${username} failed: ${found.status()}`);
  return ((await found.json()) as unknown[]).length > 0;
}

/** A Keycloak user of the shared realm, created by the baseline seed when missing. */
export type SeedUser = {
  username: string;
  password: string;
  email: string;
  firstName: string;
  lastName: string;
};

/**
 * Creates the user in the shared realm when no user with that exact user name
 * exists (Keycloak admin API, master admin from M8FLOW_E2E_MASTER_BOOTSTRAP_ADMIN_*).
 * An existing user is left as it is. Returns true when the user was created.
 */
export async function ensureKeycloakUser(page: Page, user: SeedUser): Promise<boolean> {
  const token = await keycloakAdminToken(page);
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
  const usersUrl = `${KEYCLOAK_BASE_URL}/admin/realms/${encodeURIComponent(SHARED_REALM)}/users`;
  const found = await page.request.get(`${usersUrl}?username=${encodeURIComponent(user.username)}&exact=true`, { headers });
  if (!found.ok()) {
    throw new Error(`Keycloak user lookup for ${user.username} failed: ${found.status()}`);
  }
  if (((await found.json()) as unknown[]).length) return false;
  const created = await page.request.post(usersUrl, {
    headers,
    data: {
      username: user.username,
      email: user.email,
      firstName: user.firstName,
      lastName: user.lastName,
      enabled: true,
      emailVerified: true,
      credentials: [{ type: 'password', value: user.password, temporary: false }],
    },
  });
  if (created.status() === 409) return false;
  if (!created.ok()) {
    throw new Error(`Keycloak user ${user.username} could not be created: ${created.status()}`);
  }
  return true;
}

type TenantGroupRow = { name: string; mapped_roles?: string[]; members?: { username?: string }[] };

/** The tenant's organization group with this exact name, or undefined. */
export async function findTenantGroup(page: Page, tenantId: string, name: string): Promise<TenantGroupRow | undefined> {
  const result = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/groups?search=${encodeURIComponent(name)}&limit=100`,
  );
  if (result.status !== 200) {
    throw new Error(`listing groups of tenant ${tenantId} failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  return ((result.body as { groups?: TenantGroupRow[] }).groups ?? []).find((g) => g.name === name);
}

/**
 * Makes sure the tenant has a group with this name and that the group carries
 * every listed tenant role (created with its roles when missing; a missing role
 * is added to an existing group). Returns true when the group was created.
 */
export async function ensureTenantGroup(page: Page, tenantId: string, name: string, roles: string[]): Promise<boolean> {
  const tenant = encodeURIComponent(tenantId);
  const existing = await findTenantGroup(page, tenantId, name);
  if (!existing) {
    const created = await backendFetch(page, `/v1.0/m8flow/tenants/${tenant}/groups`, {
      method: 'POST',
      data: { name, roles },
    });
    if (created.status === 201) return true;
    if (created.status !== 409) {
      throw new Error(`creating group "${name}" failed: ${created.status} ${JSON.stringify(created.body)}`);
    }
  }
  for (const role of roles) {
    if (existing?.mapped_roles?.includes(role)) continue;
    const granted = await backendFetch(
      page,
      `/v1.0/m8flow/tenants/${tenant}/groups/${encodeURIComponent(name)}/roles/${encodeURIComponent(role)}`,
      { method: 'PUT' },
    );
    if (granted.status >= 300) {
      throw new Error(`giving group "${name}" the ${role} role failed: ${granted.status} ${JSON.stringify(granted.body)}`);
    }
  }
  return false;
}

/** Puts an existing tenant member into one of the tenant's groups (safe to repeat). */
export async function assignTenantGroupMember(page: Page, tenantId: string, groupName: string, username: string): Promise<void> {
  const result = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(groupName)}/members/${encodeURIComponent(username)}`,
    { method: 'PUT' },
  );
  if (result.status >= 300 && result.status !== 409) {
    throw new Error(`adding ${username} to group "${groupName}" failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

export async function removeTenantMember(page: Page, tenantId: string, username: string): Promise<void> {
  const result = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/members/${encodeURIComponent(username)}`,
    { method: 'DELETE' },
  );
  if (result.status !== 200 && result.status !== 404) {
    throw new Error(`removeTenantMember failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

export async function getSeedTenant(page: Page): Promise<TenantRecord> {
  return getTenantBySlug(page, SEED_TENANT_SLUG);
}

// ---------------------------------------------------------------------------
// Test-data cleanup for invitation tests.
// Invited mock users (e2e-*@example.test) are real Keycloak users once the
// invitation is accepted. M8Flow has no "delete user" API, so cleanup:
//   1. revokes any still-PENDING invitation for the address (M8Flow API),
//   2. removes the user from the tenant (M8Flow API),
//   3. deletes the user from the shared Keycloak realm (Keycloak Admin API,
//      master bootstrap admin -- M8FLOW_E2E_MASTER_BOOTSTRAP_ADMIN_*).
// Every step is best effort: a cleanup problem is logged, never fails a test.
// ---------------------------------------------------------------------------

type InvitationListItem = { id: string; email: string; status: string };

function isMockTestEmail(value: string | undefined): boolean {
  const v = (value ?? '').toLowerCase();
  return v.startsWith('e2e-') && v.endsWith(`@${MOCK_EMAIL_DOMAIN}`);
}

async function listTenantInvitations(page: Page, tenantId: string): Promise<InvitationListItem[]> {
  const result = await backendFetch(
    page,
    `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/invitations?status=PENDING&limit=100`,
  );
  if (result.status !== 200) {
    throw new Error(`list invitations failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  return ((result.body as { results?: InvitationListItem[] })?.results ?? []);
}

async function revokePendingInvitations(
  page: Page,
  tenantId: string,
  matches: (email: string) => boolean,
): Promise<number> {
  let revoked = 0;
  for (const invitation of await listTenantInvitations(page, tenantId)) {
    if (invitation.status !== 'PENDING' || !matches(invitation.email)) continue;
    const result = await backendFetch(
      page,
      `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/invitations/${encodeURIComponent(invitation.id)}`,
      { method: 'DELETE' },
    );
    if (result.status === 200) revoked += 1;
  }
  return revoked;
}

async function keycloakAdminToken(page: Page): Promise<string> {
  const admin = masterBootstrapAdminCredentials();
  const response = await page.request.post(
    `${KEYCLOAK_BASE_URL}/realms/master/protocol/openid-connect/token`,
    {
      form: {
        grant_type: 'password',
        client_id: 'admin-cli',
        username: admin.username,
        password: admin.password,
      },
    },
  );
  if (!response.ok()) {
    throw new Error(`Keycloak admin token failed: ${response.status()} ${await response.text()}`);
  }
  return ((await response.json()) as { access_token: string }).access_token;
}

/** Deletes shared-realm Keycloak users whose e-mail/username matches. */
async function deleteKeycloakUsers(
  page: Page,
  search: string,
  matches: (user: { username?: string; email?: string }) => boolean,
): Promise<number> {
  const token = await keycloakAdminToken(page);
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
  const usersUrl = `${KEYCLOAK_BASE_URL}/admin/realms/${encodeURIComponent(SHARED_REALM)}/users`;
  const list = await page.request.get(`${usersUrl}?search=${encodeURIComponent(search)}&max=500`, { headers });
  if (!list.ok()) {
    throw new Error(`Keycloak user search failed: ${list.status()} ${await list.text()}`);
  }
  let deleted = 0;
  for (const user of (await list.json()) as Array<{ id: string; username?: string; email?: string }>) {
    if (!matches(user)) continue;
    const response = await page.request.delete(`${usersUrl}/${encodeURIComponent(user.id)}`, { headers });
    if (response.ok()) deleted += 1;
  }
  return deleted;
}

async function bestEffort(label: string, action: () => Promise<unknown>): Promise<void> {
  try {
    await action();
  } catch (error) {
    console.warn(`[cleanup] ${label} skipped: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * Removes one invited mock user: pending invitation, tenant membership and
 * Keycloak account. `page` must be signed in as super-admin.
 */
export async function cleanupInvitedUser(page: Page, tenantId: string, email: string): Promise<void> {
  const target = email.toLowerCase();
  await bestEffort(`revoke invitation for ${email}`, () =>
    revokePendingInvitations(page, tenantId, (e) => e.toLowerCase() === target),
  );
  await bestEffort(`remove ${email} from tenant`, () => removeTenantMember(page, tenantId, email));
  await bestEffort(`delete Keycloak user ${email}`, () =>
    deleteKeycloakUsers(page, email, (u) => [u.email, u.username].some((v) => (v ?? '').toLowerCase() === target)),
  );
}

/**
 * Sweeps mock data left behind by earlier runs (e.g. a run that was stopped
 * before its cleanup ran): pending e2e-* invitations in the tenant and
 * e2e-*@example.test users in the shared realm. `page` must be super-admin.
 */
export async function cleanupLeftoverMockUsers(page: Page, tenantId: string): Promise<void> {
  await bestEffort('revoke leftover e2e invitations', async () => {
    const n = await revokePendingInvitations(page, tenantId, isMockTestEmail);
    if (n) console.log(`[cleanup] Revoked ${n} leftover e2e invitation(s).`);
  });
  await bestEffort('delete leftover e2e Keycloak users', async () => {
    const n = await deleteKeycloakUsers(page, `@${MOCK_EMAIL_DOMAIN}`, (u) => isMockTestEmail(u.email ?? u.username));
    if (n) console.log(`[cleanup] Deleted ${n} leftover e2e user(s) from Keycloak.`);
  });
}
