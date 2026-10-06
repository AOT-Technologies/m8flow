import * as React from "react"
import { Select as SelectPrimitive } from "radix-ui"
import { CheckIcon, ChevronDownIcon } from "lucide-react"

import { cn } from "@/lib/utils"

// forwardRef throughout (not the shadcn-CLI-generated plain function
// components) for the same reason as ui/dialog.tsx: this app is on React 18,
// and Radix's internal Presence needs a real ref forwarded to the DOM node
// to detect animation completion.

const Select = SelectPrimitive.Root
const SelectGroup = SelectPrimitive.Group
const SelectValue = SelectPrimitive.Value

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentProps<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    data-slot="select-trigger"
    className={cn(
      // Same box as ui/input.tsx so selects line up with text fields in forms.
      "flex h-8 w-full items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-2.5 text-sm whitespace-nowrap text-foreground outline-none hover:border-foreground/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-placeholder:text-muted-foreground data-[state=open]:border-ring [&>span]:line-clamp-1",
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = "SelectTrigger"

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentProps<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", collisionPadding = 8, sideOffset = 4, ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      data-slot="select-content"
      position={position}
      collisionPadding={collisionPadding}
      sideOffset={sideOffset}
      className={cn(
        // Bracket form, not the bare `data-open:`/`data-closed:` variant —
        // same fix as ui/dialog.tsx: Tailwind v4's bare form matches a
        // literal boolean attribute, but Radix sets a valued
        // `data-state="open"|"closed"` here (confirmed against
        // @radix-ui/react-select's source), so the bare form was dead CSS.
        // Same panel as ui/dropdown-menu.tsx; height capped to what Radix
        // measures as available so it never runs off the viewport/modal.
        "relative z-50 max-h-[min(24rem,var(--radix-select-content-available-height))] min-w-[8rem] overflow-hidden rounded-xl border border-border bg-card text-foreground shadow-md data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
        position === "popper" &&
          className
      )}
      {...props}
    >
      <SelectPrimitive.Viewport
        className={cn(
          "p-1.5",
          position === "popper" &&
            "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]"
        )}
      >
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
))
SelectContent.displayName = "SelectContent"

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentProps<typeof SelectPrimitive.Item> & {
    /** Helper line under the label; shown in the menu only, not the trigger. */
    description?: React.ReactNode
  }
>(({ className, children, description, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    data-slot="select-item"
    className={cn(
      // Matches DropdownMenuRadioItem: leading checkmark + medium weight for
      // the selected row, neutral bg-muted for hover/keyboard highlight.
      "relative flex w-full cursor-pointer gap-2 rounded-lg py-2 pr-2.5 pl-2 text-sm text-foreground outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-muted data-[state=checked]:font-medium",
      description ? "items-start" : "items-center",
      className
    )}
    {...props}
  >
    <span aria-hidden className="flex size-4 shrink-0 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <CheckIcon className="size-4 text-nav-active" strokeWidth={2.5} />
      </SelectPrimitive.ItemIndicator>
    </span>
    <span className="flex min-w-0 flex-1 flex-col">
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      {description ? (
        <span className="text-xs font-normal text-muted-foreground">{description}</span>
      ) : null}
    </span>
  </SelectPrimitive.Item>
))
SelectItem.displayName = "SelectItem"

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectItem,
}
