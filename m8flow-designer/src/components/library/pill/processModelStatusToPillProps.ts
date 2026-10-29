import type { VariantProps } from "class-variance-authority"
import type { ParseKeys } from "i18next"

import i18n from "@/i18n"
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
const STATUS_CONFIG: Record<ProcessModelStatus, { labelKey: ParseKeys; tone: PillTone }> = {
  published: { labelKey: "common.modelStatus.published", tone: "success" },
  draft: { labelKey: "common.modelStatus.draft", tone: "muted" },
  paused: { labelKey: "common.modelStatus.paused", tone: "warning" },
}

/**
 * Absent / unrecognised reads as `published`, matching the backend's own
 * default (`catalog.process_model_status`) and api.yml. The API always sends
 * one of the three values, so this only fires under version skew — and
 * defaulting to `draft` there would mark every legacy model Draft and strip
 * its Start button while the backend happily starts it.
 */
export function normalizeProcessModelStatus(
  status: ProcessModelStatus | null | undefined,
): ProcessModelStatus {
  return status && status in STATUS_CONFIG ? status : "published"
}

/** Versioned publishing: a published model whose working copy differs from
 * its live version reads "Published – Unpublished changes". Start still runs
 * the live version, so the tone stays healthy-adjacent (info), not a warning. */
function showsUnpublishedChanges(
  status: ProcessModelStatus | null | undefined,
  hasUnpublishedChanges: boolean | null | undefined,
): boolean {
  return Boolean(hasUnpublishedChanges) && normalizeProcessModelStatus(status) === "published"
}

export function processModelStatusToPillProps(
  status: ProcessModelStatus | null | undefined,
  hasUnpublishedChanges?: boolean | null,
): {
  tone: PillTone
  dot: boolean
  children: string
} {
  if (showsUnpublishedChanges(status, hasUnpublishedChanges)) {
    return { tone: "info", dot: true, children: i18n.t("common.modelStatus.publishedWithChanges") }
  }
  const config = STATUS_CONFIG[normalizeProcessModelStatus(status)]
  return { tone: config.tone, dot: true, children: i18n.t(config.labelKey) }
}

/** One-line explanation of what the lifecycle status means for starting
 * instances — shown next to the status pill on the detail page and modeler. */
const STATUS_HINT: Record<ProcessModelStatus, ParseKeys> = {
  draft: "common.modelStatusHint.draft",
  published: "common.modelStatusHint.published",
  paused: "common.modelStatusHint.paused",
}

export function processModelStatusHint(
  status: ProcessModelStatus | null | undefined,
  hasUnpublishedChanges?: boolean | null,
): string {
  if (showsUnpublishedChanges(status, hasUnpublishedChanges)) {
    return i18n.t("common.modelStatusHint.publishedWithChanges")
  }
  return i18n.t(STATUS_HINT[normalizeProcessModelStatus(status)])
}
