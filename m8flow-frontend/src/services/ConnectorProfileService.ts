/**
 * Connector profile API calls.
 *
 * HttpService is callback-based, so each call is wrapped in a promise here, to
 * keep the views free of nested callbacks.
 */
import HttpService from './HttpService';
import type {
  ConnectorProfile,
  ConnectorTemplate,
} from '../components/bpmn/connectorProfileStore';

export type { ConnectorProfile, ConnectorTemplate };

/** The payload a create or update sends. Secret values are write-only. */
export interface ConnectorProfilePayload {
  connector_type?: string;
  profile_name?: string;
  display_name?: string;
  description?: string | null;
  config?: Record<string, unknown>;
  is_active?: boolean;
}

const call = <T,>(opts: {
  path: string;
  httpMethod?: string;
  postBody?: unknown;
}): Promise<T> =>
  new Promise((resolve, reject) => {
    HttpService.makeCallToBackend({
      path: opts.path,
      httpMethod: opts.httpMethod ?? 'GET',
      postBody: opts.postBody,
      successCallback: resolve as (result: unknown) => void,
      failureCallback: reject,
    });
  });

export const fetchConnectorTemplate = (
  connectorType: string,
): Promise<ConnectorTemplate> =>
  call({ path: `/m8flow/connector-templates/${connectorType}` });

export const fetchConnectorTemplates = (): Promise<ConnectorTemplate[]> =>
  call({ path: '/m8flow/connector-templates' });

/**
 * Profiles for one connector.
 *
 * Inactive profiles are included: the management UI must keep showing a
 * deactivated profile so it stays visible and recoverable.
 */
export const fetchConnectorProfiles = (
  connectorType?: string,
): Promise<ConnectorProfile[]> =>
  call({
    path: connectorType
      ? `/m8flow/connector-profiles?connector_type=${encodeURIComponent(connectorType)}`
      : '/m8flow/connector-profiles',
  });

export const fetchConnectorProfile = (
  profileId: number,
): Promise<ConnectorProfile> =>
  call({ path: `/m8flow/connector-profiles/${profileId}` });

export const createConnectorProfile = (
  payload: ConnectorProfilePayload,
): Promise<ConnectorProfile> =>
  call({
    path: '/m8flow/connector-profiles',
    httpMethod: 'POST',
    postBody: payload,
  });

export const updateConnectorProfile = (
  profileId: number,
  payload: ConnectorProfilePayload,
): Promise<ConnectorProfile> =>
  call({
    path: `/m8flow/connector-profiles/${profileId}`,
    httpMethod: 'PUT',
    postBody: payload,
  });

/**
 * Deactivate a profile, or remove it permanently with ``hard``.
 *
 * Soft delete is the default because a process model may still name the profile:
 * deactivating makes such a run fail loudly and stays reversible, whereas a hard
 * delete also destroys the stored credentials.
 */
export const deleteConnectorProfile = (
  profileId: number,
  hard = false,
): Promise<unknown> =>
  call({
    path: `/m8flow/connector-profiles/${profileId}${hard ? '?hard=true' : ''}`,
    httpMethod: 'DELETE',
  });

export const reactivateConnectorProfile = (
  profileId: number,
): Promise<ConnectorProfile> =>
  updateConnectorProfile(profileId, { is_active: true });

/**
 * Pull a human-readable message out of a failed call.
 *
 * The backend returns field-level validation problems under `task_data.detail`
 * in the shape `{loc, msg, type}`, so the form can put each message back on the
 * field that caused it.
 */
export const profileErrorMessage = (error: any): string =>
  error?.message ||
  error?.error_line ||
  'Something went wrong. Please try again.';

export const profileFieldErrors = (error: any): Record<string, string> => {
  const detail = error?.task_data?.detail;
  if (!Array.isArray(detail)) {
    return {};
  }
  const errors: Record<string, string> = {};
  detail.forEach((item: any) => {
    // loc is ["config", "<field>"] for a field problem, ["profile_name"] for the
    // name; take the last element either way.
    const loc = Array.isArray(item?.loc) ? item.loc : [];
    const field = loc[loc.length - 1];
    if (typeof field === 'string' && item?.msg) {
      errors[field] = item.msg;
    }
  });
  return errors;
};
