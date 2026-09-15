import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const pillVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs leading-none font-semibold whitespace-nowrap",
  {
    variants: {
      // Mirrors `ui/badge.tsx`'s pale-surface + saturated-text pattern
      // (`bg-{tone}/10 text-{tone}`) rather than reinventing it. The
      // mockup's tone label is "error" but this codebase's token is
      // "destructive" — mapped here, not renamed at the token level.
      tone: {
        success: "bg-success/10 text-success",
        error: "bg-destructive/10 text-destructive",
        warning: "bg-warning/10 text-warning",
        muted: "bg-muted text-muted-foreground",
        // Matches `ui/badge.tsx`'s own `info` variant and `library/alert`'s
        // `info` tone exactly (`bg-info/10 text-info`) — not the
        // page-local `bg-nav-active/15 text-info` "Primary" badge look,
        // which uses a different token/opacity and isn't this app's actual
        // "info" convention (confirmed against `Badge`'s `info` variant).
        info: "bg-info/10 text-info",
      },
    },
    defaultVariants: {
      tone: "muted",
    },
  }
)

// Keyed identically to `pillVariants`'s `tone` so the leading dot always
// matches the pill's own saturated text color. Kept as a separate lookup
// (rather than folded into the `cva` config above) because the dot is a
// nested child element, not a class applied to the pill root.
const pillDotToneClassName: Record<
  NonNullable<VariantProps<typeof pillVariants>["tone"]>,
  string
> = {
  success: "bg-success",
  error: "bg-destructive",
  warning: "bg-warning",
  muted: "bg-muted-foreground",
  info: "bg-info",
}

export interface PillProps
  extends React.ComponentPropsWithoutRef<"span">,
    VariantProps<typeof pillVariants> {
  /**
   * Leading status-color dot. Defaults to `true`. Set `false` for the
   * mockup's plain static tag pill pattern (e.g. "Ticketmaster API" /
   * "Spotify OAuth") — same visual family as the status-dot pill, just
   * without the dot and without tone carrying any status meaning.
   */
  dot?: boolean
}

function Pill({
  className,
  tone = "muted",
  dot = true,
  children,
  ...props
}: PillProps) {
  const resolvedTone = tone ?? "muted"

  return (
    <span
      data-slot="pill"
      data-tone={resolvedTone}
      className={cn(pillVariants({ tone: resolvedTone }), className)}
      {...props}
    >
      {dot ? (
        <span
          aria-hidden="true"
          data-slot="pill-dot"
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            pillDotToneClassName[resolvedTone]
          )}
        />
      ) : null}
      {children}
    </span>
  )
}

export { Pill, pillVariants }
