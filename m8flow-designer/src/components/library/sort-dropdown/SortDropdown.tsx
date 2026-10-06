import * as React from "react"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export interface SortDropdownOption {
  label: string
  value: string
  /** Muted, right-aligned count shown in the menu only — never in the trigger. */
  count?: number
  /** One-line helper text under the label, for options that need explaining. */
  description?: string
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
 * inventing a second dropdown component for what's visually identical.
 * Rows are `DropdownMenuRadioItem`s: selected = checkmark + medium weight,
 * hover/keyboard focus = neutral `bg-muted`. Keep the "all" option's label
 * short (e.g. "All") so the trigger never repeats itself ("Status: All", not
 * "Status: Any status").
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
              "flex min-w-[200px] items-center gap-2.5 rounded-full border border-border bg-card px-4 py-2.5 text-[13.5px] text-foreground outline-none hover:border-foreground/30 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-[state=open]:border-nav-active",
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
        <DropdownMenuContent
          align="start"
          className="min-w-[max(220px,var(--radix-dropdown-menu-trigger-width))]"
        >
          <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
            {options.map((option) => (
              <DropdownMenuRadioItem
                key={option.value}
                value={option.value}
                className={option.description ? "items-start" : undefined}
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate">{option.label}</span>
                  {option.description ? (
                    <span className="text-xs font-normal text-muted-foreground">
                      {option.description}
                    </span>
                  ) : null}
                </span>
                {/* Whitespace node: invisible in flex layout, but keeps the
                    accessible name "Draft 0" rather than "Draft0". */}{" "}
                {option.count !== undefined ? (
                  <span className="ml-4 text-xs font-normal text-muted-foreground tabular-nums">
                    {option.count}
                  </span>
                ) : null}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }
)
SortDropdown.displayName = "SortDropdown"

export { SortDropdown }
