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
  const result = String(raw).toLowerCase() === 'true';
  // #region agent log
  if (typeof window !== 'undefined') {
    fetch('http://127.0.0.1:7243/ingest/603ec126-81cd-4be3-ba0d-84501c09e628', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hypothesisId: 'A',
        location: 'useConfig.ts:getEnableMultitenant',
        message: 'Multitenant config source',
        data: { runtime, build, raw, result },
        timestamp: Date.now(),
        sessionId: 'debug-session',
      }),
    }).catch(() => {});
  }
  // #endregion
  return result;
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
