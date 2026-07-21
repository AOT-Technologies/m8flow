import {
  ConsoleTransport,
  FetchTransport,
  getWebInstrumentations,
  initializeFaro,
  type Faro,
} from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';

declare global {
  interface Window {
    spiffworkflowFrontendJsenv?: Record<string, string | undefined>;
  }
}

const SENSITIVE_KEY_PATTERN =
  /authorization|token|password|secret|cookie|email|username|m8flow_selected_tenant/i;

let faroInstance: Faro | null = null;

function runtimeConfig(key: string): string | undefined {
  return window.spiffworkflowFrontendJsenv?.[key];
}

function collectorUrl(): string | undefined {
  return (
    runtimeConfig('M8FLOW_FARO_COLLECTOR_URL') ||
    import.meta.env.VITE_M8FLOW_FARO_COLLECTOR_URL
  );
}

function parseSampleRate(raw: string | undefined, fallback: number): number {
  if (!raw) {
    return fallback;
  }
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function scrubValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(scrubValue);
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (SENSITIVE_KEY_PATTERN.test(key)) {
        out[key] = '[redacted]';
      } else {
        out[key] = scrubValue(nested);
      }
    }
    return out;
  }
  return value;
}

export function initFaro(): Faro | null {
  if (faroInstance) {
    return faroInstance;
  }

  const url = collectorUrl();
  if (!url) {
    return null;
  }

  const tracingSampleRate = parseSampleRate(
    runtimeConfig('M8FLOW_FARO_TRACING_SAMPLE_RATE'),
    0.2,
  );

  faroInstance = initializeFaro({
    app: {
      name: 'm8flow-frontend',
      version: '1.0.0',
      environment: runtimeConfig('M8FLOW_FRONTEND_ENV') || 'local_development',
    },
    instrumentations: [
      ...getWebInstrumentations(),
      new TracingInstrumentation({ instrumentationOptions: { propagateTraceHeaderCorsUrls: [] } }),
    ],
    transports: [
      new FetchTransport({ url, apiKey: runtimeConfig('M8FLOW_FARO_API_KEY') }),
      new ConsoleTransport(),
    ],
    sessionTracking: {
      samplingRate: tracingSampleRate,
    },
    beforeSend: (item) => scrubValue(item) as typeof item,
  });

  return faroInstance;
}

export function getFaro(): Faro | null {
  return faroInstance;
}

export function readTenantCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)m8flow_selected_tenant=([^;]*)/);
  if (!match?.[1]) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export function syncFaroTenantFromCookie(): void {
  const faro = getFaro();
  if (!faro) {
    return;
  }
  const tenantId = readTenantCookie();
  if (!tenantId) {
    return;
  }
  faro.api.setUser({ attributes: { m8flow_tenant_id: tenantId } });
}

export function pushFaroError(error: unknown): void {
  const faro = getFaro();
  if (!faro) {
    return;
  }
  if (error instanceof Error) {
    faro.api.pushError(error);
    return;
  }
  faro.api.pushError(new Error(String(error)));
}
