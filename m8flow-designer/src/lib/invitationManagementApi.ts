import { apiFetch, apiGet, ApiError } from './api';

import type { TenantRole } from './tenantAdminApi';

export type InvitationManagementStatus = 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED';

export type TenantInvitation = {
  id: string;
  tenant_id: string;
  email: string;
  roles: string[];
  status: InvitationManagementStatus;
  expires_at_in_seconds: number;
  accepted_at_in_seconds?: number | null;
  created_by: string;
  created_at_in_seconds: number;
  invitation_link?: string;
};

export type TenantInvitationList = {
  tenant_id: string;
  results: TenantInvitation[];
  total: number;
  offset: number;
  limit: number;
};

export type TenantInvitationResponse = {
  tenant_id: string;
  invitation: TenantInvitation;
};

type InvitationListQuery = {
  status?: InvitationManagementStatus;
  offset?: number;
  limit?: number;
};

function invitationsPath(tenantId: string, suffix = ''): string {
  return `/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}/invitations${suffix}`;
}

function withQuery(path: string, query: InvitationListQuery = {}): string {
  const params = new URLSearchParams();
  if (query.status) {
    params.set('status', query.status);
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

export function invitationManagementErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.serverMessage) {
    return error.serverMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function fetchTenantInvitations(
  tenantId: string,
  query: InvitationListQuery = {},
): Promise<TenantInvitationList> {
  return apiGet<TenantInvitationList>(withQuery(invitationsPath(tenantId), query));
}

export function createTenantInvitation(
  tenantId: string,
  payload: { email: string; roles: TenantRole[]; validity_days?: number },
): Promise<TenantInvitationResponse> {
  const body: { email: string; roles: TenantRole[]; validity_days?: number } = {
    email: payload.email,
    roles: payload.roles,
  };
  if (payload.validity_days !== undefined) {
    body.validity_days = payload.validity_days;
  }
  return jsonFetch<TenantInvitationResponse>(invitationsPath(tenantId), {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function resendTenantInvitation(
  tenantId: string,
  invitationId: string,
): Promise<TenantInvitationResponse> {
  return jsonFetch<TenantInvitationResponse>(
    invitationsPath(tenantId, `/${encodeURIComponent(invitationId)}/resend`),
    { method: 'POST' },
  );
}

export function revokeTenantInvitation(
  tenantId: string,
  invitationId: string,
): Promise<TenantInvitationResponse> {
  return jsonFetch<TenantInvitationResponse>(
    invitationsPath(tenantId, `/${encodeURIComponent(invitationId)}`),
    { method: 'DELETE' },
  );
}
