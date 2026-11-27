import { pathForApiVersion, resolveApiVersion } from './apiVersionConfig';

export const API_VERSION = resolveApiVersion(import.meta.env.VITE_API_VERSION);
export const API_VERSION_PREFIX = `/v${API_VERSION}`;

/** Replace a versioned or unversioned API path with the configured prefix. */
export function apiVersionPath(path: string): string {
  return pathForApiVersion(path, API_VERSION);
}
