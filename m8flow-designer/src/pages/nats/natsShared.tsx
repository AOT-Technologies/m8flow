import type { ReactNode } from 'react';

import type { PillProps } from '@/components/library/pill/Pill';
import { ApiError } from '@/lib/api';
import type { NatsStreamMessage } from '@/lib/natsApi';

export type Tone = NonNullable<PillProps['tone']>;

const numberFormat = new Intl.NumberFormat('en-US');

// Missing values render as "—", never as a made-up 0.
export function formatNumber(value: number | null | undefined): string {
  return value == null ? '—' : numberFormat.format(value);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${units[unit]}`;
}

/** Compact duration from seconds: 90 -> "1m 30s", 604800 -> "7d". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  const units: [string, number][] = [['d', 86400], ['h', 3600], ['m', 60], ['s', 1]];
  const parts: string[] = [];
  let rest = Math.max(0, Math.floor(seconds));
  for (const [unit, size] of units) {
    if (rest >= size) {
      parts.push(`${Math.floor(rest / size)}${unit}`);
      rest %= size;
    }
    if (parts.length === 2) break;
  }
  return parts.length ? parts.join(' ') : '0s';
}

/** NATS reports "no timestamp" as the zero time (0001-01-01); treat it as missing. */
export function parseNatsTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) || ms <= 0 ? null : ms;
}

export function formatDateTime(epochSeconds: number | null | undefined): string {
  return epochSeconds ? new Date(epochSeconds * 1000).toLocaleString() : '—';
}

const OUTCOME_LABELS: Record<string, string> = {
  queued: 'Queued',
  instantiated: 'Started',
  duplicate: 'Duplicate',
  invalid_payload: 'Invalid payload',
  rejected_auth: 'Rejected: auth',
  rejected_scope: 'Rejected: scope',
  tenant_mismatch: 'Tenant mismatch',
  user_not_found: 'User not found',
  model_not_found: 'Process not found',
  transient_error: 'Error',
};

/** Event sources in Event history; the worker decides which stream an event came from. */
export const NATS_EVENT_SOURCES = [
  { worker: 'consumer', label: 'Trigger events' },
  { worker: 'notification_worker', label: 'Notifications' },
] as const;

/** For a notification a successful outcome means the email went out, not that a process started. */
export function outcomeLabel(outcome: string, worker?: string): string {
  if (outcome === 'instantiated' && worker === 'notification_worker') return 'Sent';
  return OUTCOME_LABELS[outcome] ?? outcome;
}

export function outcomeTone(outcome: string): Tone {
  if (outcome === 'instantiated') return 'success';
  if (outcome === 'queued') return 'info';
  if (outcome === 'duplicate') return 'muted';
  return 'error';
}

/** Coarse on purpose: makes "something is wrong" visible, not an SLA. */
export function backlogTone(pending: number): Tone {
  if (pending === 0) return 'success';
  if (pending < 100) return 'info';
  if (pending < 1000) return 'warning';
  return 'error';
}

/** Pretty-prints JSON payloads; binary and truncated previews are shown as-is. */
export function formatPayload(message: Pick<NatsStreamMessage, 'payload' | 'encoding' | 'truncated'>): string {
  if (message.encoding !== 'utf-8' || message.truncated) return message.payload;
  try {
    return JSON.stringify(JSON.parse(message.payload), null, 2);
  } catch {
    return message.payload;
  }
}

/** A disabled or stopped broker is an expected state; the backend message says which. */
export function natsErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.serverMessage) return err.serverMessage;
    if (err.status === 503) return 'The NATS server is not reachable. It may be stopped or still starting.';
    return err.message;
  }
  return 'Could not load NATS monitoring data.';
}

/** Shown instead of payload actions when the backend reports inspection is off. */
export const INSPECTION_DISABLED_HINT =
  'Message payload inspection is disabled on this deployment (set M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED=true to enable it).';

/** Heading used by every tab's cards. */
export function CardHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h2 className="text-[15px] font-semibold text-foreground">{title}</h2>
        {subtitle && <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
