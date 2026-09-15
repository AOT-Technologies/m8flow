import * as React from "react"

import { cn } from "@/lib/utils"

export interface SpinnerProps extends React.ComponentPropsWithoutRef<"span"> {
  /**
   * Ring diameter in pixels. Defaults to `16`, matching the mockup's
   * "Loading spinner" example.
   */
  size?: number
  /** Accessible label for screen readers. Defaults to `"Loading"`. */
  label?: string
}

function Spinner({ className, size = 16, label = "Loading", style, ...props }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label}
      data-slot="spinner"
      className={cn(
        // Tailwind v4 ships `animate-spin` as a default utility — no custom
        // `@keyframes` needed here (unlike Skeleton's shimmer, which has no
        // built-in equivalent). Matches the mockup's `aot-spin` rotate.
        "inline-block shrink-0 rounded-full border-2 border-border border-t-nav-active animate-spin",
        className
      )}
      style={{ width: size, height: size, ...style }}
      {...props}
    />
  )
}

export { Spinner }
