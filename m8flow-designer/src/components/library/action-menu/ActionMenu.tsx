import * as React from "react"
import { MoreVertical } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export interface ActionMenuItem {
  label: string
  /** Optional leading icon, e.g. `<ExternalLink className="size-3.5" />`. */
  icon?: React.ReactNode
  onSelect: () => void
  /**
   * Renders the row disabled (Radix handles the `data-disabled` dimming and
   * blocks `onSelect`) rather than omitting it. Use this when a caller wants
   * the action visible-but-inert (e.g. "Save as template" pending a
   * permission check); omit the item from `items` entirely instead when it
   * shouldn't appear at all (e.g. "Delete" with no `onDelete` wired).
   */
  disabled?: boolean
  /** Tints the label/icon `text-destructive`, e.g. a "Delete" action. */
  destructive?: boolean
}

export interface ActionMenuProps {
  items: ActionMenuItem[]
  /** aria-label for the kebab trigger button, e.g. `"Instance actions"`. */
  triggerLabel?: string
  /**
   * `"row"` (default): small unbordered circle for list-row kebabs
   * (`Processes`/`Process instances` row actions). `"header"`: larger
   * bordered circle with a card background, for page-header overflow menus
   * (`Process model detail`'s header actions).
   */
  size?: "row" | "header"
  align?: "start" | "end"
  /** Classes applied to the trigger button. */
  className?: string
  /** Classes applied to the dropdown panel, e.g. to override its width. */
  contentClassName?: string
}

/**
 * Kebab-button-triggered overflow menu, wrapping `ui/dropdown-menu.tsx`.
 * Replaces the app's three independently hand-rolled "open state +
 * outside-click/Escape close" row/header action menus (component-adoption
 * map, ticket 21) with one component backed by Radix — outside-click,
 * Escape, and closing on select are handled by `DropdownMenu` itself, so
 * callers no longer manage `open` state or close-on-select by hand.
 */
const ActionMenu = React.forwardRef<HTMLButtonElement, ActionMenuProps>(
  (
    {
      items,
      triggerLabel = "More actions",
      size = "row",
      align = "end",
      className,
      contentClassName,
    },
    ref
  ) => {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            ref={ref}
            type="button"
            data-slot="action-menu-trigger"
            aria-label={triggerLabel}
            className={cn(
              "flex items-center justify-center rounded-full",
              size === "header"
                ? "size-[38px] border border-border bg-card hover:bg-muted"
                : "size-7 hover:bg-muted",
              className
            )}
          >
            <MoreVertical
              className={cn("text-muted-foreground", size === "header" ? "size-4" : "size-[15px]")}
              strokeWidth={2.4}
            />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={align} className={cn("min-w-[10rem]", contentClassName)}>
          {items.map((item) => (
            <DropdownMenuItem
              key={item.label}
              disabled={item.disabled}
              onSelect={item.onSelect}
              className={cn(
                "gap-2.5",
                item.destructive && "text-destructive data-highlighted:text-destructive"
              )}
            >
              {item.icon ? (
                <span className={item.destructive ? "text-destructive" : "text-muted-foreground"}>
                  {item.icon}
                </span>
              ) : null}
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }
)
ActionMenu.displayName = "ActionMenu"

export { ActionMenu }
