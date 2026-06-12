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

const ENABLE_MULTITENANT = getEnableMultitenant();
const SHARED_REALM_IDENTIFIER = getSharedRealmIdentifier();
const MASTER_REALM_IDENTIFIER = getMasterRealmIdentifier();

/**
 * useConfig - Hook to access configuration values
 * @returns Configuration object with all config values
 */
export function useConfig() {
  return {
    BACKEND_BASE_URL,
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
    PROCESS_STATUSES,
    SHARED_REALM_IDENTIFIER,
    SPIFF_ENVIRONMENT,
    TASK_METADATA,
    TIME_FORMAT_HOURS_MINUTES,
  };
}

export default useConfig;
