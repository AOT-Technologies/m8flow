import type { VariantProps } from "class-variance-authority"
import type { ParseKeys } from "i18next"

import i18n from "@/i18n"
import { pillVariants } from "./Pill"

type PillTone = NonNullable<VariantProps<typeof pillVariants>["tone"]>

/**
 * Reproduces the removed `StatusBadge`'s exact tone/dot/fallback lookup as
 * `Pill` props, for the process-instance-shaped status strings used across
 * the home, task-review, process-instances, and process-model-detail pages.
 * Migrated per the `m8flow-designer component adoption` map's
 * StatusBadge→Pill consolidation ticket — `StatusBadge.tsx` is gone, this is
 * the only place this status vocabulary is now encoded.
 *
 * One deliberate visual change from `StatusBadge`: `error` used to render a
 * *solid* white-on-red `Badge variant="destructive"`. `Pill`'s `tone="error"`
 * is always the tinted `bg-destructive/10 text-destructive` look (matching
 * its `success`/`warning`/`muted` siblings) — accepted as a conscious
 * softening for pill-vocabulary consistency, not an oversight.
 */
const STATUS_CONFIG: Record<string, { labelKey: ParseKeys; tone: PillTone; dot: boolean }> = {
  complete: { labelKey: "common.instanceStatus.complete", tone: "success", dot: true },
  error: { labelKey: "common.instanceStatus.error", tone: "error", dot: true },
  user_input_required: { labelKey: "common.instanceStatus.userInputRequired", tone: "warning", dot: false },
  // Same muted look as unknown statuses; listed only so they get a translated label.
  running: { labelKey: "common.instanceStatus.running", tone: "muted", dot: false },
  waiting: { labelKey: "common.instanceStatus.waiting", tone: "muted", dot: false },
  suspended: { labelKey: "common.instanceStatus.suspended", tone: "muted", dot: false },
  terminated: { labelKey: "common.instanceStatus.terminated", tone: "muted", dot: false },
  not_started: { labelKey: "common.instanceStatus.notStarted", tone: "muted", dot: false },
}

function humanize(status: string): string {
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function processInstanceStatusToPillProps(status: string): {
  tone: PillTone
  dot: boolean
  children: string
} {
  const config = STATUS_CONFIG[status]
  if (!config) return { tone: "muted", dot: false, children: humanize(status) }
  return { tone: config.tone, dot: config.dot, children: i18n.t(config.labelKey) }
}

/** Translated label for a process-instance status; unknown statuses are humanized. */
export function processInstanceStatusLabel(status: string): string {
  return processInstanceStatusToPillProps(status).children
}
