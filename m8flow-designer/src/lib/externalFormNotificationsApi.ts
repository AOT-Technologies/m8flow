import { apiGet, apiPost } from './api';

/** Stored delivery status of one external-form email (one recipient of one task). */
export type ExternalFormEmailStatus =
  | 'pending'
  | 'sending'
  | 'notified'
  | 'submitted'
  | 'completed'
  | 'failed'
  | 'expired'
  | 'superseded'
  | 'smtp_unconfigured'
  | 'cancelled';

export type ExternalFormEmail = {
  id: number;
  process_instance_id: number;
  task_guid: string;
  task_name: string | null;
  task_title: string | null;
  email: string;
  status: ExternalFormEmailStatus;
  /** `status`, except a delivered link past its expiry reads `expired`. Drive the UI from this. */
  effective_status: ExternalFormEmailStatus;
  /** Still `sending` after the worker's send lease ran out. */
  stuck_sending: boolean;
  /** Resend would be accepted on status alone; the backend still re-checks the task. */
  resendable: boolean;
  attempts: number;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
  notified_at_in_seconds: number | null;
  expires_at_in_seconds: number | null;
};

export type ExternalFormEmailList = {
  results: ExternalFormEmail[];
  pagination: { count: number; total: number; pages: number; page: number };
};

export type SmtpStatus = {
  configured: boolean;
  required_keys: string[];
  optional_keys: string[];
  missing_required_keys: string[];
  unreadable_keys: string[];
  reason: string | null;
  configured_keys: string[];
};

export type ResendResult = { ok: boolean; id: number; status: ExternalFormEmailStatus; message: string };

const BASE = '/v1.0/m8flow/external-form-notifications';

/** Super-admins name the tenant explicitly; everyone else is scoped by the tenant cookie. */
function withTenant(params: URLSearchParams, tenantId: string | null | undefined): string {
  if (tenantId) params.set('tenantId', tenantId);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export function externalFormEmailsPath(processInstanceId: number, tenantId?: string | null): string {
  const params = new URLSearchParams({ process_instance_id: String(processInstanceId), per_page: '200' });
  return `${BASE}${withTenant(params, tenantId)}`;
}

export function fetchExternalFormEmails(
  processInstanceId: number,
  tenantId?: string | null,
): Promise<ExternalFormEmailList> {
  return apiGet<ExternalFormEmailList>(externalFormEmailsPath(processInstanceId, tenantId));
}

export function resendExternalFormEmail(requestId: number, tenantId?: string | null): Promise<ResendResult> {
  const path = `${BASE}/${requestId}/resend${withTenant(new URLSearchParams(), tenantId)}`;
  return apiPost<ResendResult>(path, {});
}

export function fetchSmtpStatus(tenantId?: string | null): Promise<SmtpStatus> {
  return apiGet<SmtpStatus>(`${BASE}/smtp-status${withTenant(new URLSearchParams(), tenantId)}`);
}
