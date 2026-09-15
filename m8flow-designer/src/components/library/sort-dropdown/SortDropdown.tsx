import * as React from "react"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export interface SortDropdownOption {
  label: string
  value: string
}

export interface SortDropdownProps {
  /** Options rendered as single-select rows in the dropdown panel. */
  options: SortDropdownOption[]
  /** Controlled selected value — must match one of `options[].value`. */
  value: string
  /** Called with the newly selected option's `value` when a row is clicked. */
  onChange: (value: string) => void
  /**
   * Prefix shown before the selected option's label, e.g. `"Sort"` renders
   * "Sort: Last run". Defaults to `"Sort"` — every existing sort-dropdown
   * call site is unaffected. Override for the same pill-dropdown shape used
   * as a plain single-select filter (e.g. `label="Status"` renders
   * "Status: Active").
   */
  label?: string
  /** Classes applied to the trigger button. */
  className?: string
}

/**
 * Pill-shaped "{label}: {selected label}" trigger that opens a single-select
 * `ui/dropdown-menu.tsx` panel, per the mockup's "Dropdown" example (sort
 * options: Last run / Name / Status). `label` defaults to `"Sort"`, matching
 * the mockup exactly; overriding it reuses the same shape for a plain
 * single-select filter (component-adoption map, ticket 19) rather than
 * inventing a second dropdown component for what's visually identical. The
 * currently selected option gets a persistent pale `bg-nav-active/10` +
 * bold treatment — `DropdownMenuItem` itself only covers the transient
 * hover/keyboard-highlight state, so that per-row selection styling is
 * applied here.
 *
 * Open state is tracked locally (rather than read off the trigger's Radix
 * `data-state`) purely to drive the chevron's rotation — `DropdownMenu` is
 * otherwise fully uncontrolled/Radix-driven for outside-click/Escape.
 */
const SortDropdown = React.forwardRef<HTMLButtonElement, SortDropdownProps>(
  ({ options, value, onChange, label = "Sort", className }, ref) => {
    const [open, setOpen] = React.useState(false)
    const selected = options.find((option) => option.value === value)

    return (
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button
            ref={ref}
            type="button"
            data-slot="sort-dropdown-trigger"
            className={cn(
              "flex min-w-[200px] items-center gap-2.5 rounded-full border border-border bg-card px-4 py-2.5 text-[13.5px] text-foreground",
              className
            )}
          >
            <span className="flex-1 text-left">
              {label}: {selected?.label ?? ""}
            </span>
            <ChevronDown
              className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")}
              aria-hidden="true"
            />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[220px]">
          {options.map((option) => (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => onChange(option.value)}
              className={cn(
                option.value === value
                  ? "bg-nav-active/10 font-semibold text-foreground"
                  : "font-normal"
              )}
            >
              {option.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }
)
SortDropdown.displayName = "SortDropdown"

export { SortDropdown }
