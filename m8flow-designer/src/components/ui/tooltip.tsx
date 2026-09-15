import * as React from "react"
import { Tooltip as TooltipPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

// `Provider`/`Root` render no DOM node of their own — aliased directly, same
// as `DialogPortal = DialogPrimitive.Portal` in dialog.tsx. Everything that
// *does* render a real element is forwardRef'd (see dialog.tsx's comment on
// why: Presence's exit-animation timing needs a real ref).
const TooltipProvider = TooltipPrimitive.Provider
const Tooltip = TooltipPrimitive.Root

const TooltipTrigger = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Trigger>,
  React.ComponentProps<typeof TooltipPrimitive.Trigger>
>((props, ref) => (
  <TooltipPrimitive.Trigger ref={ref} data-slot="tooltip-trigger" {...props} />
))
TooltipTrigger.displayName = "TooltipTrigger"

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentProps<typeof TooltipPrimitive.Content>
>(({ className, side = "top", sideOffset = 8, children, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      data-slot="tooltip-content"
      side={side}
      sideOffset={sideOffset}
      className={cn(
        // Mockup's tooltip is a dark gunmetal pill with white text above
        // the trigger — --aot-gunmetal maps to --foreground per this map's
        // token decision, so the fallback text color is --background (the
        // app's near-white), not a literal white, to stay theme-consistent.
        //
        // Radix's real attribute is `data-state="delayed-open" |
        // "instant-open" | "closed"` (confirmed against the installed
        // @radix-ui/react-tooltip source) — deliberately using the
        // bracket-form `data-[state=...]` variant here rather than this
        // codebase's `data-open:`/`data-closed:` shorthand seen in
        // dialog.tsx. That shorthand compiles to a literal-boolean-attribute
        // selector (`[data-open]`), which Radix never actually sets — built
        // and inspected the compiled CSS to confirm dialog.tsx's own
        // animate-in/out classes are inert for this reason (0 occurrences
        // of `[data-state=open]` in the built CSS). Not this ticket's file
        // to fix; not repeating the same mistake in a new one.
        "z-50 rounded-lg bg-foreground px-2.5 py-1.5 text-xs font-medium text-background shadow-md data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95 data-[state=instant-open]:animate-in data-[state=instant-open]:fade-in-0",
        className
      )}
      {...props}
    >
      {children}
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
))
TooltipContent.displayName = "TooltipContent"

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
