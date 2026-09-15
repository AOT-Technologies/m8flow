import * as React from "react"

import { cn } from "@/lib/utils"

export interface EmptyStateProps extends React.ComponentPropsWithoutRef<"div"> {
  /**
   * Optional leading visual. The mockup's own example (`.dc.html`) has no
   * icon — just heading + description — so this is deliberately optional
   * rather than a required prop with a default fallback icon.
   */
  icon?: React.ReactNode
  /** Heading copy. Always a prop, never hardcoded — callers own the copy. */
  title: string
  /** Supporting copy shown under the title. Optional — some empty states
   * are heading-only. */
  description?: string
  /**
   * A slot for the action row, not named `primaryAction`/`secondaryAction`
   * props: the mockup's pair ("New process model" / "Clear filter") is one
   * concrete case, but callers may want one button, two, or none, and
   * should compose whichever `ui/button.tsx` variant fits (`pill`/
   * `pill-outline` per the mockup) rather than this component dictating
   * variant/order via two fixed named slots.
   */
  actions?: React.ReactNode
}

function EmptyState({
  className,
  icon,
  title,
  description,
  actions,
  ...props
}: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        "rounded-[14px] border border-border bg-background px-6 py-[52px] text-center",
        className
      )}
      {...props}
    >
      {icon ? (
        <div
          aria-hidden="true"
          data-slot="empty-state-icon"
          className="mb-3 flex justify-center text-muted-foreground"
        >
          {icon}
        </div>
      ) : null}
      <div
        data-slot="empty-state-title"
        className="text-[15.5px] font-semibold text-foreground"
      >
        {title}
      </div>
      {description ? (
        <p
          data-slot="empty-state-description"
          className="mt-2 mb-5 text-[13.5px] text-muted-foreground"
        >
          {description}
        </p>
      ) : null}
      {actions ? (
        <div
          data-slot="empty-state-actions"
          className={cn(
            "flex justify-center gap-2.5",
            // No description means no bottom margin was already applied to
            // push the actions down — add it here instead so the actions
            // row never sits flush against the title.
            !description && "mt-5"
          )}
        >
          {actions}
        </div>
      ) : null}
    </div>
  )
}

export { EmptyState }
