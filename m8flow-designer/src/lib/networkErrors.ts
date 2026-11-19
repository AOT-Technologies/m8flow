import i18n from '@/i18n';

// Only fetch's known transport failures: invalid URLs, headers and request bodies
// can also reject with TypeError and must retain their original diagnostics.
const FETCH_FAILURE = /^(?:failed to fetch|load failed|networkerror when attempting to fetch resource\.?)$/i;
const CHUNK_FAILURE = /^(?:failed to fetch dynamically imported module(?::.*)?|error loading dynamically imported module(?::.*)?|importing a module script failed\.?|unable to preload CSS for .+)$/i;

export class NetworkError extends Error {
  readonly cause?: unknown;

  constructor(cause?: unknown) {
    super();
    this.name = 'NetworkError';
    this.cause = cause;
  }

  // Keep the stable error type and resolve its display text when read, so a
  // locale change while a request is pending does not freeze the old language.
  get message(): string {
    return i18n.t('shell.network.unableToConnect');
  }
}

export function isFetchNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError && FETCH_FAILURE.test(error.message);
}

export function isNetworkFailure(error: unknown): boolean {
  return error instanceof NetworkError || isFetchNetworkFailure(error) ||
    (error instanceof Error && CHUNK_FAILURE.test(error.message));
}

export function toNetworkError(error: unknown): never {
  throw isFetchNetworkFailure(error) ? new NetworkError(error) : error;
}
