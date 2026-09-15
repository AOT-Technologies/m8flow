import * as React from "react"

import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export interface ModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: React.ReactNode
  /** Arbitrary body content. Deliberately not typed/structured any further
   * here — e.g. the mockup's "New group" text-input form belongs in this
   * component's own Storybook story, not baked into `Modal` itself, so any
   * other caller (including `WizardModal`) can put whatever it needs here. */
  children?: React.ReactNode
  /** Right-aligned footer action row (the mockup's Cancel/Create-group pair).
   * Omit entirely for a modal with no footer actions. */
  footer?: React.ReactNode
  /**
   * `"sm"` (460px wide, the default) is the original plain-form-modal size —
   * auto-height with no floor or cap, right for a couple of form fields.
   * `"md"` (720px wide, `min-h-[520px]` tall) is for content that needs real
   * room in both dimensions — a picker list, a multi-step wizard — without a
   * hard cap: it still auto-grows past that floor if content needs more
   * (unlike `"lg"`, nothing here forces internal scrolling). `"lg"` (1100px)
   * is for genuinely large embedded content (e.g. a code editor): it
   * additionally caps the dialog at 80vh and switches `DialogContent` to a
   * flex column with `overflow-hidden`, so `children` can fill the
   * remaining space itself via `className="min-h-0 flex-1 ..."` (the same
   * pattern callers already use for a Monaco-editor-style child) instead of
   * growing the whole dialog past the viewport.
   */
  size?: "sm" | "md" | "lg"
}

const modalSizeClassName: Record<NonNullable<ModalProps["size"]>, string> = {
  sm: "max-w-[460px] sm:max-w-[460px]",
  md: "max-w-[720px] sm:max-w-[720px] min-h-[520px] flex flex-col",
  lg: "max-w-[1100px] sm:max-w-[1100px] h-[80vh] flex flex-col overflow-hidden",
}

/**
 * General-purpose chrome around `ui/dialog.tsx`, matching the mockup's
 * "Modal" section: a title + round close (X) button in the header, arbitrary
 * body content via `children`, and a footer slot for actions. The close
 * button is `DialogContent`'s own built-in `showCloseButton`, left at its
 * default `true` — no second close button is built here.
 *
 * This is the general-purpose wrapper other things (including `WizardModal`)
 * build on top of. It intentionally does not know about any specific body
 * content or form.
 *
 * Two mockup-matched tweaks layered on top of `DialogContent`'s shadcn
 * defaults via `className`/`overlayClassName` (both are the exact per-instance
 * escape hatches `DialogContent` already exposes for this — see its own
 * comments in `ui/dialog.tsx`):
 * - The overlay tint (`rgba(44,55,60,.40)`) is darker than the shadcn default
 *   (`bg-black/10`), so it's overridden to `bg-foreground/40` (this app's
 *   `--foreground` is a dark gunmetal gray, matching the mockup's tint).
 * - `DialogContent` ships with no `shadow-*` utility at all; the mockup calls
 *   for `box-shadow: var(--shadow-lg)`, mapped onto Tailwind's own `shadow-lg`
 *   utility (the same one `ui/alert-dialog.tsx` already uses for its panel).
 */
function Modal({ open, onOpenChange, title, children, footer, size = "sm" }: ModalProps) {
  // "md" and "lg" both grow taller than the plain-form "sm" default, so both
  // get the flex-column treatment: the header/footer stay their natural
  // size (`flex-none`) and the footer is pinned to the bottom of whatever
  // height the dialog ends up at (`mt-auto`) — for "lg" that's moot (its
  // `min-h-0 flex-1` child already fills the fixed 80vh height exactly), but
  // for "md" it matters: without it, short `children` content would leave
  // the footer floating above a gap of blank space rather than at the
  // bottom of the `min-h-[520px]` floor.
  const hasHeightFloor = size === "md" || size === "lg"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-slot="modal-content"
        data-size={size}
        overlayClassName="bg-foreground/40"
        className={cn("gap-3 p-6 shadow-lg", modalSizeClassName[size])}
      >
        <DialogHeader className={hasHeightFloor ? "flex-none" : undefined}>
          <DialogTitle className="pr-6 font-display text-[19px] leading-tight font-semibold text-foreground">
            {title}
          </DialogTitle>
        </DialogHeader>
        {children}
        {footer ? (
          <DialogFooter
            data-slot="modal-footer"
            className={cn(
              "mx-0 mb-0 flex-row items-center justify-end gap-2.5 rounded-none border-t-0 bg-transparent p-0",
              hasHeightFloor && "mt-auto flex-none"
            )}
          >
            {footer}
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export { Modal }
