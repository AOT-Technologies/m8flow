import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/80",
        outline:
          "border-border bg-transparent hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
        // The mockup-matched "pill" action button family (Processes.dc.html /
        // Process Model detail): rounded-full, uppercase, letter-spaced —
        // visually distinct from the rounded-lg default scale above, so each
        // gets `size: "pill"` (an intentionally empty size — see below) to
        // avoid fighting the default size scale's own padding/height.
        // Consolidated from what were three duplicated local string constants
        // (`pillPrimary`/`pillDark`/`pillOutline` in ProcessModelOverview.tsx)
        // plus the same shapes hand-rolled again in ProcessesModelsList.tsx —
        // see .scratch/m8flow-designer-optimization/issues/08-consolidate-button-markup.md.
        pill: "rounded-full bg-nav-active px-5 py-2.5 text-[12.5px] font-semibold tracking-[0.04em] text-foreground uppercase shadow-xs",
        "pill-dark":
          "inline-flex items-center gap-2 rounded-full bg-foreground px-[18px] py-2.5 text-[12.5px] font-semibold tracking-[0.04em] text-white uppercase",
        "pill-outline":
          "gap-2 rounded-full border-2 border-border bg-card px-[18px] py-2 text-[12.5px] font-semibold tracking-[0.04em] text-foreground uppercase",
        // Same shape reused for the modeler's Save/Download confirm actions
        // (EditorDialog, SaveButton, ProcessModelModelerPage — three
        // previously-independent copies of the identical class string).
        "pill-info":
          "rounded-full bg-info px-4 py-2 text-xs font-semibold tracking-wide text-white uppercase",
        "pill-cancel":
          "rounded-full border border-border px-4 py-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase hover:bg-muted",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
        // Deliberately empty: every `pill*` variant above already carries its
        // own full padding/text-size in the variant string, so this size
        // option contributes nothing — it exists only so pill buttons can
        // pass `size="pill"` instead of leaving the default `size` (h-8
        // px-2.5 ...) active, which would otherwise fight the pill's own
        // padding via class-merge order (size is applied after variant).
        pill: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
