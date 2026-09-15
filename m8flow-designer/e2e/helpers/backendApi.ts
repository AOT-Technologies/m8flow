import { expect, type Page } from '@playwright/test';

import { cookieValue, SELECTED_TENANT_COOKIE } from './auth';
import {
  BACKEND_BASE_URL,
  PARITY_SECOND_TENANT_NAME,
  PARITY_SECOND_TENANT_SLUG,
  SEED_TENANT_LABEL,
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
  return `${prefix}-${stamp}@example.test`;
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
  return getTenantBySlug(page, SEED_TENANT_LABEL);
}
