import HttpService from '@spiffworkflow-frontend/services/HttpService';

const BASE_PATH = '/v1.0/m8flow/external-form-notifications';

export const SMTP_STATUS_PATH = '/m8flow/external-form-notifications/smtp-status';
export const NOTIFICATIONS_PATH = '/m8flow/external-form-notifications';

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
   * returned by the backend.
   */
  configured_keys: string[];
}

export interface ExternalFormNotification {
  id: number;
  process_instance_id: number;
  task_guid: string;
  email: string;
  /**
   * pending | notified | submitted | completed | failed | expired | superseded |
   * smtp_unconfigured (parked: the tenant has no usable SMTP configuration, so the
   * worker has stopped retrying it).
   */
  status: string;
  attempts: number;
  last_error: string | null;
  created_at_in_seconds: number;
  updated_at_in_seconds: number;
  notified_at_in_seconds: number | null;
  expires_at_in_seconds: number | null;
  /** Present for super-admin requests only. */
  tenantId?: string;
  tenantName?: string | null;
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

const cacheKeyFor = (tenantId?: string | null): string => tenantId || '__active__';

export interface GetSmtpStatusOptions {
  force?: boolean;
}

export const getSmtpStatus = (
  tenantId?: string | null,
  options?: GetSmtpStatusOptions | boolean,
): Promise<SmtpStatus> => {
  const force = typeof options === 'boolean' ? options : Boolean(options?.force);
  const key = cacheKeyFor(tenantId);
  if (force) {
    smtpStatusByTenant.delete(key);
  }
  const cached = smtpStatusByTenant.get(key);
  if (cached) {
    return cached;
  }

  const path = tenantId
    ? `${BASE_PATH}/smtp-status?tenantId=${encodeURIComponent(tenantId)}`
    : `${BASE_PATH}/smtp-status`;

  // Drop a rejected lookup from the cache so a transient failure (or a 400 a super admin
  // gets before choosing a tenant) does not stick for the rest of the session.
  const pending = callBackend<SmtpStatus>({ path }).catch((error) => {
    smtpStatusByTenant.delete(key);
    throw error;
  });
  smtpStatusByTenant.set(key, pending);
  return pending;
};

/** Forget a cached verdict, e.g. after the admin saves a secret. */
export const clearSmtpStatusCache = (tenantId?: string | null): void => {
  if (tenantId === undefined) {
    smtpStatusByTenant.clear();
    return;
  }
  smtpStatusByTenant.delete(cacheKeyFor(tenantId));
};

export const getNotifications = (opts?: {
  processInstanceId?: number;
  status?: string;
  page?: number;
  perPage?: number;
  tenantId?: string | null;
}): Promise<ExternalFormNotificationPage> => {
  const query = new URLSearchParams();
  if (opts?.processInstanceId !== undefined) {
    query.set('process_instance_id', String(opts.processInstanceId));
  }
  if (opts?.status) query.set('status', opts.status);
  if (opts?.page !== undefined) query.set('page', String(opts.page));
  if (opts?.perPage !== undefined) query.set('per_page', String(opts.perPage));
  if (opts?.tenantId) query.set('tenantId', opts.tenantId);

  const suffix = query.toString() ? `?${query.toString()}` : '';
  return callBackend<ExternalFormNotificationPage>({
    path: `${BASE_PATH}${suffix}`,
  });
};

/**
 * Requeue one notification. The worker delivers it on its next sweep, so this is not
 * instantaneous.
 */
export const resendNotification = (
  requestId: number,
  tenantId?: string | null,
): Promise<{ ok: boolean; id: number; status: string; message: string }> => {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  return callBackend({
    path: `${BASE_PATH}/${requestId}/resend${suffix}`,
    httpMethod: 'POST',
    postBody: {},
  });
};

export default {
  getSmtpStatus,
  clearSmtpStatusCache,
  getNotifications,
  resendNotification,
};
