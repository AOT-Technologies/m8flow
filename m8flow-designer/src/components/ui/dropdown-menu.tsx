import * as React from "react"
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui"
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"

// forwardRef throughout — same reasoning as dialog.tsx/tooltip.tsx (Radix's
// Presence-driven mount/unmount needs a real ref).
//
// A note on which `data-*` variant form is used where, learned the hard way
// while building ui/tooltip.tsx (ticket 02): Radix's *content* elements set
// `data-state="open"|"closed"` (a **valued** attribute — needs the bracket
// form `data-[state=open]:`), but its *item* elements set `data-highlighted`
// and `data-disabled` as **boolean presence** attributes (`data-highlighted=""`
// when active, the attribute omitted entirely otherwise) — confirmed against
// the installed `@radix-ui/react-menu` source. That boolean form is exactly
// what Tailwind v4's bare `data-highlighted:`/`data-disabled:` variant
// matches, so the bare form is correct *there*, not a repeat of dialog.tsx's
// mistake. Mixing the two up either way silently produces dead CSS.

const DropdownMenu = DropdownMenuPrimitive.Root

const DropdownMenuTrigger = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Trigger>,
  React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>
>((props, ref) => (
  <DropdownMenuPrimitive.Trigger ref={ref} data-slot="dropdown-menu-trigger" {...props} />
))
DropdownMenuTrigger.displayName = "DropdownMenuTrigger"

const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentProps<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 6, collisionPadding = 8, ...props }, ref) => (
  <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.Content
      ref={ref}
      data-slot="dropdown-menu-content"
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={cn(
        // Capped to the space Radix measures as available so long lists
        // scroll instead of running off the viewport.
        "z-50 max-h-[var(--radix-dropdown-menu-content-available-height)] min-w-[8rem] overflow-x-hidden overflow-y-auto rounded-xl border border-border bg-card p-1.5 text-foreground shadow-md data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
        className
      )}
      {...props}
    />
  </DropdownMenuPrimitive.Portal>
))
DropdownMenuContent.displayName = "DropdownMenuContent"

const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentProps<typeof DropdownMenuPrimitive.Item>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    data-slot="dropdown-menu-item"
    className={cn(
      // Hover/keyboard highlight is a neutral `bg-muted` on every menu row;
      // selection (see DropdownMenuRadioItem) is a checkmark + weight, never a
      // background, so the two states can't be confused.
      "relative flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-foreground outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-muted",
      className
    )}
    {...props}
  />
))
DropdownMenuItem.displayName = "DropdownMenuItem"

const DropdownMenuCheckboxItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.CheckboxItem>,
  React.ComponentProps<typeof DropdownMenuPrimitive.CheckboxItem>
>(({ className, children, checked, ...props }, ref) => (
  <DropdownMenuPrimitive.CheckboxItem
    ref={ref}
    data-slot="dropdown-menu-checkbox-item"
    checked={checked}
    className={cn(
      "relative flex cursor-pointer items-center gap-2.5 rounded-lg py-2 pr-2.5 pl-2.5 text-sm text-foreground outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-muted",
      className
    )}
    {...props}
  >
    <span
      aria-hidden
      className="flex size-4 shrink-0 items-center justify-center rounded-[4px] border-[1.5px] border-border data-[state=checked]:border-none data-[state=checked]:bg-nav-active"
      data-state={checked ? "checked" : "unchecked"}
    >
      <DropdownMenuPrimitive.ItemIndicator>
        <Check className="size-3 text-white" strokeWidth={3} />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
    {children}
  </DropdownMenuPrimitive.CheckboxItem>
))
DropdownMenuCheckboxItem.displayName = "DropdownMenuCheckboxItem"

const DropdownMenuRadioGroup = DropdownMenuPrimitive.RadioGroup

/**
 * Single-select row: reserved leading checkmark slot (so labels align whether
 * or not the row is selected), `font-medium` when selected, neutral
 * `bg-muted` highlight. Radix gives it `role="menuitemradio"` + `aria-checked`.
 */
const DropdownMenuRadioItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.RadioItem>,
  React.ComponentProps<typeof DropdownMenuPrimitive.RadioItem>
>(({ className, children, ...props }, ref) => (
  <DropdownMenuPrimitive.RadioItem
    ref={ref}
    data-slot="dropdown-menu-radio-item"
    className={cn(
      "relative flex cursor-pointer items-center gap-2 rounded-lg py-2 pr-2.5 pl-2 text-sm text-foreground outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-muted data-[state=checked]:font-medium",
      className
    )}
    {...props}
  >
    <span aria-hidden className="flex size-4 shrink-0 items-center justify-center">
      <DropdownMenuPrimitive.ItemIndicator>
        <Check className="size-4 text-nav-active" strokeWidth={2.5} />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
    {children}
  </DropdownMenuPrimitive.RadioItem>
))
DropdownMenuRadioItem.displayName = "DropdownMenuRadioItem"

const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Separator>,
  React.ComponentProps<typeof DropdownMenuPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Separator
    ref={ref}
    data-slot="dropdown-menu-separator"
    className={cn("-mx-1 my-1.5 h-px bg-border", className)}
    {...props}
  />
))
DropdownMenuSeparator.displayName = "DropdownMenuSeparator"

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
}
