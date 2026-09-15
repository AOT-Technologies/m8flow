import * as React from "react"

import { cn } from "@/lib/utils"

export interface SkeletonProps extends React.ComponentPropsWithoutRef<"span"> {
  /** CSS width (any valid value, e.g. `"70%"`, `240`, `"100%"`). Defaults to `"100%"`. */
  width?: string | number
  /** CSS height (any valid value, e.g. `14`, `"1rem"`). Defaults to `14`. */
  height?: string | number
}

function Skeleton({ className, width = "100%", height = 14, style, ...props }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      data-slot="skeleton"
      className={cn(
        // No built-in Tailwind shimmer utility exists (unlike Spinner's
        // `animate-spin`), so this uses the `shimmer` `@keyframes` appended
        // to src/styles/index.css, referenced here via Tailwind's arbitrary
        // animation syntax rather than a hand-rolled CSS module — matches
        // the mockup's `aot-shimmer` timing/easing exactly.
        "block shrink-0 rounded-[6px] bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--muted)_25%,var(--background)_50%,var(--muted)_75%)] animate-[shimmer_1.4s_ease-in-out_infinite]",
        className
      )}
      style={{ width, height, ...style }}
      {...props}
    />
  )
}

export { Skeleton }
