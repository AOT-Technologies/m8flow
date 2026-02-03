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

function getEnableMultitenant(): boolean {
  const runtime =
    typeof window !== 'undefined' &&
    (window as Window & { spiffworkflowFrontendJsenv?: { MULTI_TENANT_ON?: string } })
      ?.spiffworkflowFrontendJsenv?.MULTI_TENANT_ON;
  const build =
    typeof import.meta !== 'undefined' && import.meta.env
      ? (import.meta.env.VITE_MULTI_TENANT_ON as string | undefined)
      : undefined;
  const raw = runtime ?? build ?? '';
  return String(raw).toLowerCase() === 'true';
}

const ENABLE_MULTITENANT = getEnableMultitenant();

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
    PROCESS_STATUSES,
    SPIFF_ENVIRONMENT,
    TASK_METADATA,
    TIME_FORMAT_HOURS_MINUTES,
  };
}

export default useConfig;
