import type { NatsEventOutcome } from "../../services/NatsMonitoringService";
import { NATS_FAILURE_OUTCOMES } from "../../services/NatsMonitoringService";

/**
 * Shared formatting for the NATS monitoring panels.
 *
 * Labels go through `translate(key, fallback)` — the pattern already used by
 * PendingInvitationsPanel — so the panels read correctly in English immediately and
 * translations can be filled in per locale without blocking the feature.
 */
export type Translate = (key: string, fallback: string) => string;

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${units[unit]}`;
}

export function formatNumber(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString();
}

/**
 * CPU load from /varz, which NATS reports as a fractional percentage. Rendered to one
 * decimal so the API can keep full precision without the UI showing 0.7500000000000001,
 * and trimmed back to a whole number when the fraction is zero.
 */
export function formatPercent(value: number | null | undefined): string {
  const percent = value ?? 0;
  return Number.isInteger(percent) ? String(percent) : percent.toFixed(1);
}

export function formatEpochSeconds(seconds: number | null | undefined): string {
  if (!seconds) {
    return "—";
  }
  return new Date(seconds * 1000).toLocaleString();
}

/** Compact "3m ago" style age, for last-activity columns. */
export function formatAge(seconds: number | null | undefined, translate: Translate): string {
  if (!seconds) {
    return "—";
  }
  const delta = Math.max(0, Math.floor(Date.now() / 1000) - seconds);
  if (delta < 60) {
    return translate("nats_age_seconds", "{{n}}s ago").replace("{{n}}", String(delta));
  }
  if (delta < 3600) {
    return translate("nats_age_minutes", "{{n}}m ago").replace(
      "{{n}}",
      String(Math.floor(delta / 60)),
    );
  }
  if (delta < 86400) {
    return translate("nats_age_hours", "{{n}}h ago").replace(
      "{{n}}",
      String(Math.floor(delta / 3600)),
    );
  }
  return translate("nats_age_days", "{{n}}d ago").replace(
    "{{n}}",
    String(Math.floor(delta / 86400)),
  );
}

export type ChipColor = "default" | "success" | "warning" | "error" | "info";

export function outcomeColor(outcome: NatsEventOutcome | string): ChipColor {
  if (outcome === "instantiated") {
    return "success";
  }
  if (outcome === "queued") {
    return "info";
  }
  if (outcome === "duplicate") {
    return "default";
  }
  return NATS_FAILURE_OUTCOMES.includes(outcome as NatsEventOutcome) ? "error" : "default";
}

const OUTCOME_LABELS: Record<string, string> = {
  queued: "Queued",
  instantiated: "Started",
  duplicate: "Duplicate",
  invalid_payload: "Invalid payload",
  rejected_auth: "Rejected: auth",
  rejected_scope: "Rejected: scope",
  tenant_mismatch: "Tenant mismatch",
  user_not_found: "User not found",
  model_not_found: "Process not found",
  transient_error: "Error",
};

export function outcomeLabel(outcome: string, translate: Translate): string {
  return translate(`nats_outcome_${outcome}`, OUTCOME_LABELS[outcome] ?? outcome);
}

/**
 * Severity for a backlog figure. Thresholds are deliberately coarse: the point is to make
 * "something is wrong" visible at a glance, not to encode an SLA the project has not set.
 */
export function backlogColor(pending: number): ChipColor {
  if (pending === 0) {
    return "success";
  }
  if (pending < 100) {
    return "info";
  }
  if (pending < 1000) {
    return "warning";
  }
  return "error";
}

export function redeliveryColor(redelivered: number): ChipColor {
  if (redelivered === 0) {
    return "success";
  }
  return redelivered < 10 ? "warning" : "error";
}

/**
 * Pretty-prints a message payload for display when it looks like JSON (the common case --
 * event payloads are almost always JSON bodies). Binary/base64 payloads and truncated
 * previews are left as-is: a truncated JSON string is cut mid-object and would just fail to
 * parse, and base64 content was never JSON to begin with.
 */
export function formatPayloadPreview(payload: {
  payload: string;
  encoding: string;
  truncated: boolean;
}): string {
  if (payload.encoding !== "utf-8" || payload.truncated) {
    return payload.payload;
  }
  try {
    return JSON.stringify(JSON.parse(payload.payload), null, 2);
  } catch {
    return payload.payload;
  }
}

/** Message for a failed panel load; a disabled broker is an expected state, not a crash. */
export function loadErrorMessage(error: any, translate: Translate): string {
  const code = error?.error_code;
  if (code === "nats_monitoring_disabled") {
    return translate(
      "nats_monitoring_disabled_message",
      "NATS monitoring is not enabled on this deployment.",
    );
  }
  if (code === "nats_monitoring_unavailable") {
    return translate(
      "nats_monitoring_unavailable_message",
      "The NATS server could not be reached. It may be stopped or still starting.",
    );
  }
  if (code === "nats_message_inspection_disabled") {
    return translate(
      "nats_inspection_disabled_message",
      "Message payload inspection is disabled on this deployment.",
    );
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return translate("nats_load_failed", "Could not load NATS monitoring data.");
}
