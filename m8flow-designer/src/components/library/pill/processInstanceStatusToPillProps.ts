import type { VariantProps } from "class-variance-authority"

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
const STATUS_CONFIG: Record<string, { label: string; tone: PillTone; dot: boolean }> = {
  complete: { label: "Complete", tone: "success", dot: true },
  error: { label: "Error", tone: "error", dot: true },
  user_input_required: { label: "User Input Required", tone: "warning", dot: false },
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
  const config = STATUS_CONFIG[status] ?? { label: humanize(status), tone: "muted" as const, dot: false }
  return { tone: config.tone, dot: config.dot, children: config.label }
}
