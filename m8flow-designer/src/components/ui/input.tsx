import * as React from "react"

import { cn } from "@/lib/utils"

// The `shadcn` CLI generated this as a plain function component with no
// `ref` prop, which only works under React 19's newer ref-as-prop support.
// This app is on React 18 (see package.json) — a plain function component
// can't receive a `ref` at all under 18 ("Function components cannot be
// given refs" / the ref is silently dropped), so this is wrapped in
// `React.forwardRef` to actually support it (needed live: CallActivitySearchDialog
// focuses this input programmatically on dialog open — see
// .scratch/m8flow-designer-optimization/issues/09-extract-input-dialog-primitives.md).
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        data-slot="input"
        ref={ref}
        className={cn(
          "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
          className
        )}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
