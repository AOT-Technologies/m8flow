import { API_BASE_URL, ApiError } from './api';

export type InvitationValidation = {
  email: string;
  tenant_id: string;
  tenant_name: string;
  roles: string[];
  expires_at_in_seconds: number;
};

export type AcceptInvitationResult = {
  email: string;
  tenant_id: string;
  tenant_name: string;
  roles: string[];
  smtp_configured?: boolean;
};

async function readServerMessage(response: Response): Promise<string | undefined> {
  try {
    const data = await response.clone().json();
    const message = (data as { message?: unknown })?.message;
    return typeof message === 'string' && message.trim() ? message : undefined;
  } catch {
    return undefined;
  }
}

async function publicJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (!response.ok) {
    throw new ApiError(
      path,
      response.status,
      init.method ?? 'GET',
      await readServerMessage(response),
    );
  }
  return (await response.json()) as T;
}

export function invitationErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.serverMessage) {
    return error.serverMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function validateInvitation(token: string): Promise<InvitationValidation> {
  return publicJson<InvitationValidation>(
    `/v1.0/m8flow/invitations/validate?token=${encodeURIComponent(token)}`,
  );
}

export function acceptInvitation(
  token: string,
  password: string,
): Promise<AcceptInvitationResult> {
  return publicJson<AcceptInvitationResult>('/v1.0/m8flow/invitations/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });
}
