import type { VariantProps } from "class-variance-authority"

import type { ProcessModelStatus } from "@/lib/api"
import { pillVariants } from "./Pill"

type PillTone = NonNullable<VariantProps<typeof pillVariants>["tone"]>

/**
 * Process *model* publish lifecycle (M8F-508) — distinct from
 * `processInstanceStatusToPillProps`, which maps a process *instance*'s run
 * status. Kept as its own lookup because the two vocabularies are unrelated:
 * a model is draft/published/paused, an instance is complete/error/waiting.
 *
 * Tones follow the design mockup: published reads as healthy (green), paused
 * as an attention state (amber), draft as inert (muted).
 */
const STATUS_CONFIG: Record<ProcessModelStatus, { label: string; tone: PillTone }> = {
  published: { label: "Published", tone: "success" },
  draft: { label: "Draft", tone: "muted" },
  paused: { label: "Paused", tone: "warning" },
}

export function processModelStatusToPillProps(status: ProcessModelStatus | null | undefined): {
  tone: PillTone
  dot: boolean
  children: string
} {
  // An unknown/absent status renders as Draft rather than an empty cell — the
  // blank column this ticket was filed for.
  const config = STATUS_CONFIG[status as ProcessModelStatus] ?? STATUS_CONFIG.draft
  return { tone: config.tone, dot: true, children: config.label }
}
