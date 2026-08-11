import HttpService from './HttpService';

/**
 * One NATS_SMTP_* field, shaped like a connector config field so the shared
 * SecretFieldsForm can render it. The list is served by the backend so the key names
 * have a single definition (external_form_notification_service.SMTP_CONFIG_FIELDS).
 */
export interface SmtpConfigField {
  id: string;
  secretKey: string;
  label: string;
  type: 'text' | 'password';
  required: boolean;
  format?: 'url' | 'email' | 'port' | 'number';
  helpText?: string;
}

export interface SmtpStatus {
  /** True when every required key is set to a usable value. */
  configured: boolean;
  /** Keys without which no external form email can be sent. */
  required_keys: string[];
  optional_keys: string[];
  /** Required keys that are not usable — absent, blank, or undecryptable. */
  missing_required_keys: string[];
  /**
   * Subset of the above whose secret exists but does not resolve (blank, or the backend
   * encryption key changed). Re-entering the key is not the fix for these.
   */
  unreadable_keys?: string[];
  /** Backend explanation of why sending is blocked; null when configured. */
  reason?: string | null;
  /**
   * Keys with a usable (decryptable, non-blank) value. Names only — values are never
   * returned. Presence of a blank or undecryptable secret does not count.
   */
  configured_keys: string[];
  fields: SmtpConfigField[];
}

export const SMTP_STATUS_PATH = '/m8flow/external-form-notifications/smtp-status';
const NOTIFICATIONS_PATH = '/m8flow/external-form-notifications';

export interface ExternalFormNotification {
  id: number;
  process_instance_id: number;
  task_guid: string;
  email: string;
  status: string;
  attempts: number;
  last_error: string | null;
  created_at_in_seconds: number;
  updated_at_in_seconds: number;
  notified_at_in_seconds: number | null;
  expires_at_in_seconds: number | null;
}

export interface ExternalFormNotificationPage {
  results: ExternalFormNotification[];
  pagination: { count: number; total: number; pages: number };
}

const callBackend = <T,>(opts: {
  path: string;
  httpMethod?: string;
  postBody?: any;
}): Promise<T> =>
  new Promise((resolve, reject) => {
    HttpService.makeCallToBackend({
      path: opts.path,
      httpMethod: opts.httpMethod ?? 'GET',
      postBody: opts.postBody,
      successCallback: resolve as (result: any) => void,
      failureCallback: reject,
    });
  });

/**
 * In-flight/settled SMTP status, shared across callers, keyed by tenant.
 *
 * Both the Secrets page banner and the BPMN modeler's External Form group ask for this,
 * potentially at the same time; caching the promise means one request answers both and a
 * re-mount does not refetch.
 *
 * The key matters: a super admin can switch the tenant they are viewing, and the answer is
 * per-tenant. A single unkeyed entry would keep showing the first tenant's verdict for the
 * rest of the session.
 */
const smtpStatusByTenant = new Map<string, Promise<SmtpStatus>>();

const cacheKey = (tenantId?: string | null): string => tenantId ?? '';

export const getSmtpStatus = (tenantId?: string | null): Promise<SmtpStatus> => {
  const key = cacheKey(tenantId);
  const cached = smtpStatusByTenant.get(key);
  if (cached) {
    return cached;
  }
  const path = tenantId
    ? `${SMTP_STATUS_PATH}?tenantId=${encodeURIComponent(tenantId)}`
    : SMTP_STATUS_PATH;
  const pending = callBackend<SmtpStatus>({ path }).catch((error) => {
    // Don't cache failures: a 403 for one user, or the 400 a super admin gets before
    // picking a tenant, must not poison the result for the rest of the session.
    smtpStatusByTenant.delete(key);
    throw error;
  });
  smtpStatusByTenant.set(key, pending);
  return pending;
};

/** Drop cached statuses. Pass a tenant to invalidate just that one. */
export const clearSmtpStatusCache = (tenantId?: string | null): void => {
  if (tenantId === undefined) {
    smtpStatusByTenant.clear();
  } else {
    smtpStatusByTenant.delete(cacheKey(tenantId));
  }
};

export const listNotifications = (
  params: {
    processInstanceId?: number;
    status?: string;
    page?: number;
    perPage?: number;
    /** Super admins only; other callers are scoped by the backend. */
    tenantId?: string | null;
  } = {},
): Promise<ExternalFormNotificationPage> => {
  const query = new URLSearchParams();
  query.set('page', String(params.page ?? 1));
  query.set('per_page', String(params.perPage ?? 20));
  if (params.processInstanceId !== undefined) {
    query.set('process_instance_id', String(params.processInstanceId));
  }
  if (params.status) {
    query.set('status', params.status);
  }
  if (params.tenantId) {
    query.set('tenantId', params.tenantId);
  }
  return callBackend<ExternalFormNotificationPage>({
    path: `${NOTIFICATIONS_PATH}?${query.toString()}`,
  });
};

/** Requeue one notification. The worker retries it on its next sweep, not immediately. */
export const resendNotification = (
  id: number,
  tenantId?: string | null,
): Promise<unknown> => {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  return callBackend({
    path: `${NOTIFICATIONS_PATH}/${id}/resend${suffix}`,
    httpMethod: 'POST',
  });
};

export default {
  getSmtpStatus,
  clearSmtpStatusCache,
  listNotifications,
  resendNotification,
};
