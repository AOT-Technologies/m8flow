import * as React from "react"

import { cn } from "@/lib/utils"

function Card({
  className,
  size = "default",
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & {
  size?: "default" | "sm"
  /**
   * `default` is shadcn's own generated look (`rounded-xl` +
   * `ring-1 ring-foreground/10`) — left untouched because `StatCard.tsx`,
   * the one existing consumer, had this exact look HITL-confirmed against
   * the Home mockup ("looks good", see
   * .scratch/m8flow-designer-home/issues/07-stat-cards.md) before this
   * ticket existed; changing the default risked silently invalidating an
   * already-approved visual result this session can't re-verify live.
   *
   * `bordered` is the *other* card look already established independently
   * across ~5 files before this ticket (`rounded-2xl border border-border
   * bg-card shadow-xs`) — consolidated here instead, as its own variant,
   * rather than overloading `default` to mean two different things. Also
   * cancels the base's own gap/vertical padding (`gap-0 py-0`): every
   * existing consumer of this look manages its own internal section
   * spacing via plain child divs (headers/content with their own
   * border-b/px/py), not `CardHeader`/`CardContent`'s spacing model, so
   * the base's own `gap-(--card-spacing)`/`py-(--card-spacing)` would add
   * unwanted extra space around them. See
   * .scratch/m8flow-designer-optimization/issues/11-consolidate-card-container-markup.md.
   */
  variant?: "default" | "bordered"
}) {
  return (
    <div
      data-slot="card"
      data-size={size}
      data-variant={variant}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-xl bg-card py-(--card-spacing) text-sm text-card-foreground ring-1 ring-foreground/10 [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-xl *:[img:last-child]:rounded-b-xl",
        variant === "bordered" &&
          "gap-0 rounded-2xl border border-border py-0 shadow-xs ring-0",
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-t-xl px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-base leading-snug font-medium group-data-[size=sm]/card:text-sm",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-(--card-spacing)", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center rounded-b-xl border-t bg-muted/50 p-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
