/**
 * Backend HTTP client. Token auth, GET 401 retry, text fetch, PUT.
 */
import { BACKEND_BASE_URL } from '@spiffworkflow-frontend/config';
import { objectIsEmpty } from '@spiffworkflow-frontend/helpers';
import { getStoredGlobalTenantId } from '../contexts/GlobalTenantContext';
import UserService from './UserService';

export const HttpMethods = {
  GET: 'GET',
  POST: 'POST',
  PUT: 'PUT',
  DELETE: 'DELETE',
} as const;

const STATUS_PHRASE: Record<number, string> = {
  400: 'Bad Request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  413: 'Payload Too Large',
  500: 'Internal Server Error',
  502: 'Bad Gateway',
  503: 'Service Unavailable',
};

type CallArgs = {
  path: string;
  successCallback: Function;
  failureCallback?: Function;
  onUnauthorized?: Function;
  httpMethod?: string;
  extraHeaders?: object;
  postBody?: any;
  /** Tenant captured by the workflow action, rather than re-read at send time. */
  tenantId?: string;
};

type RawExchange = { response: Response; text: string };
type NormalizedErrorResult = Record<string, unknown> & { message: string };

export class UnauthenticatedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UnauthenticatedError';
  }
}

export class UnexpectedResponseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UnexpectedResponseError';
  }
}

export const getBasicHeaders = (): Record<string, string> => {
  const out: Record<string, string> = {};
  const token = UserService.getAccessToken();
  if (token) {
    out.Authorization = `Bearer ${token}`;
  }
  return out;
};

export const messageForHttpError = (code: number, phrase: string) => {
  const bits = [`HTTP Error ${code}`];
  if (phrase) {
    bits.push(phrase);
  } else if (STATUS_PHRASE[code]) {
    bits.push(STATUS_PHRASE[code]);
  }
  return bits.length > 1 ? `${bits[0]}: ${bits[1]}` : bits[0];
};

const normalizeErrorResult = (
  payload: unknown,
  statusCode: number,
  statusText: string,
): NormalizedErrorResult => {
  const fallbackMessage = messageForHttpError(statusCode, statusText);

  if (payload && typeof payload === 'object') {
    const normalized = { ...payload } as Record<string, unknown>;
    const existingMessage =
      typeof normalized.message === 'string' ? normalized.message.trim() : '';
    if (existingMessage) {
      return normalized as NormalizedErrorResult;
    }

    const detailMessage =
      typeof normalized.detail === 'string' ? normalized.detail.trim() : '';
    if (detailMessage) {
      normalized.message = detailMessage;
      return normalized as NormalizedErrorResult;
    }

    const titleMessage =
      typeof normalized.title === 'string' ? normalized.title.trim() : '';
    normalized.message = titleMessage || fallbackMessage;
    return normalized as NormalizedErrorResult;
  }

  return { message: fallbackMessage };
};

const looksLikeHtmlDocument = (body: string) => {
  const head = body.trimStart().slice(0, 16).toLowerCase();
  return head.startsWith('<!') || head.startsWith('<html');
};

const stripVersionPrefix = (path: string) => path.replace(/^\/v1\.0/, '');

const getSuperAdminTenantHeaders = (
  httpMethod: string,
  tenantId?: string,
): Record<string, string> => {
  if (httpMethod === HttpMethods.GET || !UserService.isSuperAdmin()) {
    return {};
  }

  const selectedTenantId = (tenantId ?? getStoredGlobalTenantId()).trim();
  if (!selectedTenantId) {
    return {};
  }

  return {
    'X-M8Flow-Tenant-Id': selectedTenantId,
  };
};

const assembleFetchInit = ({
  httpMethod = 'GET',
  extraHeaders = {},
  postBody = {},
  tenantId,
}: Pick<CallArgs, 'httpMethod' | 'extraHeaders' | 'postBody' | 'tenantId'>): RequestInit => {
  const headers = getBasicHeaders();
  Object.assign(headers, getSuperAdminTenantHeaders(httpMethod, tenantId));
  if (!objectIsEmpty(extraHeaders)) {
    Object.assign(headers, extraHeaders);
  }

  const init: RequestInit = {
    method: httpMethod,
    credentials: 'include',
  };

  if (postBody instanceof FormData) {
    init.body = postBody;
  } else if (typeof postBody === 'object') {
    if (!objectIsEmpty(postBody)) {
      init.body = JSON.stringify(postBody);
      headers['Content-Type'] = 'application/json';
    }
  } else {
    init.body = postBody;
  }

  init.headers = new Headers(headers as HeadersInit);
  return init;
};

const exchangeOnce = ({
  path,
  httpMethod,
  extraHeaders,
  postBody,
  tenantId,
}: Pick<CallArgs, 'path' | 'httpMethod' | 'extraHeaders' | 'postBody' | 'tenantId'>): Promise<RawExchange> => {
  const url = `${BACKEND_BASE_URL}${stripVersionPrefix(path)}`;
  return fetch(url, assembleFetchInit({ httpMethod, extraHeaders, postBody, tenantId })).then(
    (response) => response.text().then((text) => ({ response, text })),
  );
};

const mayRetryGetAfter401 = (method: string, alreadyRetried: boolean) =>
  !alreadyRetried && method === HttpMethods.GET;

const withGetAuthRetry = (
  method: string,
  run: () => Promise<RawExchange>,
  alreadyRetried = false,
): Promise<RawExchange> =>
  run().then((exchange) => {
    if (exchange.response.status !== 401) {
      return exchange;
    }
    if (mayRetryGetAfter401(method, alreadyRetried)) {
      return withGetAuthRetry(method, run, true);
    }
    throw new UnauthenticatedError('You must be authenticated to do this.');
  });

const parseJsonOrThrow = (exchange: RawExchange) => {
  try {
    return JSON.parse(exchange.text);
  } catch (err) {
    const statusLine = messageForHttpError(
      exchange.response.status,
      exchange.response.statusText,
    );
    let detail = `Received unexpected response from server. ${statusLine}.`;
    if (looksLikeHtmlDocument(exchange.text)) {
      detail +=
        ' The response was HTML (e.g. the app index page) instead of JSON. ' +
        'Ensure the backend is running (e.g. port 8000) and that VITE_BACKEND_BASE_URL points to it; ' +
        'when using npm start with a relative URL, the Vite proxy forwards /v1.0 to the backend.';
    }
    console.error(`${detail} Body: ${exchange.text}`);
    if (err instanceof SyntaxError) {
      throw new UnexpectedResponseError(detail);
    }
    throw err;
  }
};

const redirectHomeIfUnauthenticated = (err: any) => {
  if (err?.name !== 'UnauthenticatedError') {
    return false;
  }
  if (window.location.pathname !== '/login') {
    UserService.redirectToLogin();
  }
  return true;
};

const makeCallToBackend = ({
  path,
  successCallback,
  failureCallback,
  onUnauthorized,
  httpMethod = 'GET',
  extraHeaders = {},
  postBody = {},
  tenantId,
}: CallArgs) => {
  withGetAuthRetry(httpMethod, () =>
    exchangeOnce({ path, httpMethod, extraHeaders, postBody, tenantId }),
  )
    .then((exchange) => {
      const payload = parseJsonOrThrow(exchange);

      if (exchange.response.status === 403) {
        const normalizedError = normalizeErrorResult(
          payload,
          exchange.response.status,
          exchange.response.statusText,
        );
        if (onUnauthorized) {
          onUnauthorized(normalizedError);
        } else if (UserService.isPublicUser()) {
          window.location.href = '/public/sign-out';
        } else {
          alert(normalizedError.message);
        }
        return;
      }

      if (!exchange.response.ok) {
        const normalizedError = normalizeErrorResult(
          payload,
          exchange.response.status,
          exchange.response.statusText,
        );
        if (failureCallback) {
          failureCallback(normalizedError);
          return;
        }
        console.error(normalizedError.message);
        alert(normalizedError.message);
        return;
      }

      successCallback(payload);
    })
    .catch((err) => {
      if (redirectHomeIfUnauthenticated(err)) {
        return;
      }
      if (failureCallback) {
        failureCallback(err);
      } else {
        console.error(err.message);
      }
    });
};

/**
 * Same auth as JSON calls; returns raw response text (e.g. BPMN XML).
 */
const fetchTextFromBackend = (
  path: string,
  successCallback: (text: string) => void,
  failureCallback?: (err: unknown) => void,
) => {
  withGetAuthRetry(HttpMethods.GET, () =>
    exchangeOnce({ path, httpMethod: HttpMethods.GET }),
  )
    .then(({ response, text }) => {
      if (response.ok) {
        successCallback(text);
        return;
      }
      failureCallback?.(
        new Error(response.statusText || `HTTP ${response.status}`),
      );
    })
    .catch((err) => {
      if (redirectHomeIfUnauthenticated(err)) {
        return;
      }
      failureCallback?.(err);
    });
};

const HttpService = {
  HttpMethods,
  makeCallToBackend,
  fetchTextFromBackend,
  messageForHttpError,
  getBasicHeaders,
};

export default HttpService;
