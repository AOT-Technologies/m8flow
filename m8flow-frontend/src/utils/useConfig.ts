/**
 * useConfig - Hook for accessing configuration variables in extensions
 *
 * Provides access to all configuration values from config.tsx plus extension-only
 * flags (e.g. ENABLE_MULTITENANT from MULTI_TENANT_ON via VITE_MULTI_TENANT_ON or runtime jsenv).
 */

import {
  BACKEND_BASE_URL,
  CONFIGURATION_ERRORS,
  DARK_MODE_ENABLED,
  DATE_FORMAT,
  DATE_FORMAT_CARBON,
  DATE_FORMAT_FOR_DISPLAY,
  DATE_RANGE_DELIMITER,
  DATE_TIME_FORMAT,
  DOCUMENTATION_URL,
  PROCESS_STATUSES,
  SPIFF_ENVIRONMENT,
  TASK_METADATA,
  TIME_FORMAT_HOURS_MINUTES,
} from '@spiffworkflow-frontend/config';

export function getRuntimeOrBuildConfig(name: string): string | undefined {
  const runtime =
    typeof window !== 'undefined'
      ? (
          window as Window & {
            spiffworkflowFrontendJsenv?: Record<string, string | undefined>;
          }
        )?.spiffworkflowFrontendJsenv?.[name]
      : undefined;
  const build =
    typeof import.meta !== 'undefined' && import.meta.env
      ? ((import.meta.env as Record<string, string | undefined>)[`VITE_${name}`] as
          | string
          | undefined)
      : undefined;
  return runtime ?? build ?? undefined;
}

export function getEnableMultitenant(): boolean {
  const raw = getRuntimeOrBuildConfig('MULTI_TENANT_ON') ?? '';
  return String(raw).toLowerCase() === 'true';
}

export function getSharedRealmIdentifier(): string {
  return getRuntimeOrBuildConfig('M8FLOW_KEYCLOAK_SHARED_REALM') || 'm8flow';
}

export function getMasterRealmIdentifier(): string {
  return getRuntimeOrBuildConfig('M8FLOW_KEYCLOAK_MASTER_REALM') || 'master';
}

export function getCeleryFlowerUrl(): string {
  return getRuntimeOrBuildConfig('M8FLOW_CELERY_FLOWER_URL') || '';
}

export function getNatsUiUrl(): string {
  return getRuntimeOrBuildConfig('M8FLOW_NATS_UI_URL') || '';
}

export function getMcpServerUrl(): string {
  return getRuntimeOrBuildConfig('M8FLOW_MCP_SERVER_URL') || '';
}

const ENABLE_MULTITENANT = getEnableMultitenant();
const SHARED_REALM_IDENTIFIER = getSharedRealmIdentifier();
const MASTER_REALM_IDENTIFIER = getMasterRealmIdentifier();
const CELERY_FLOWER_URL = getCeleryFlowerUrl();
const NATS_UI_URL = getNatsUiUrl();
// NATS monitoring is optional/disabled by default; surface it only when a UI URL is configured.
const NATS_MONITORING_ENABLED = Boolean(NATS_UI_URL);
const MCP_SERVER_URL = getMcpServerUrl();
// The MCP connection page is optional; surface it only when a server URL is configured.
const MCP_CONNECTION_ENABLED = Boolean(MCP_SERVER_URL);

/**
 * useConfig - Hook to access configuration values
 * @returns Configuration object with all config values
 */
export function useConfig() {
  return {
    BACKEND_BASE_URL,
    CELERY_FLOWER_URL,
    CONFIGURATION_ERRORS,
    DARK_MODE_ENABLED,
    DATE_FORMAT,
    DATE_FORMAT_CARBON,
    DATE_FORMAT_FOR_DISPLAY,
    DATE_RANGE_DELIMITER,
    DATE_TIME_FORMAT,
    DOCUMENTATION_URL,
    ENABLE_MULTITENANT,
    MASTER_REALM_IDENTIFIER,
    MCP_CONNECTION_ENABLED,
    MCP_SERVER_URL,
    NATS_MONITORING_ENABLED,
    NATS_UI_URL,
    PROCESS_STATUSES,
    SHARED_REALM_IDENTIFIER,
    SPIFF_ENVIRONMENT,
    TASK_METADATA,
    TIME_FORMAT_HOURS_MINUTES,
  };
}

export default useConfig;
