import * as React from "react"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Chip } from "@/components/library/chip/Chip"

export interface MultiSelectDropdownOption {
  label: string
  value: string
}

export interface MultiSelectDropdownProps {
  /** Options rendered as checkbox rows in the dropdown panel. */
  options: MultiSelectDropdownOption[]
  /** Controlled selected values — each must match one of `options[].value`. */
  values: string[]
  /** Called with the full next selection whenever a row is toggled or cleared. */
  onChange: (values: string[]) => void
  /** Trigger label shown when `values` is empty. */
  placeholder?: string
  /** Classes applied to the trigger button. */
  className?: string
}

/**
 * Pill-shaped multi-select trigger (shows a placeholder or "N selected")
 * that opens a `ui/dropdown-menu.tsx` panel of `DropdownMenuCheckboxItem`
 * rows plus a "Clear selection" row, per the mockup's "Dropdown — multi
 * select" example. Selected values are also rendered below the trigger as
 * removable `library/chip` chips, matching the mockup's wrapped chip row.
 */
const MultiSelectDropdown = React.forwardRef<HTMLButtonElement, MultiSelectDropdownProps>(
  ({ options, values, onChange, placeholder = "Filter by status", className }, ref) => {
    const [open, setOpen] = React.useState(false)

    const toggleValue = (optionValue: string, checked: boolean) => {
      onChange(
        checked ? [...values, optionValue] : values.filter((value) => value !== optionValue)
      )
    }

    const removeValue = (optionValue: string) => {
      onChange(values.filter((value) => value !== optionValue))
    }

    const selectedOptions = options.filter((option) => values.includes(option.value))

    return (
      <div data-slot="multi-select-dropdown">
        <DropdownMenu open={open} onOpenChange={setOpen}>
          <DropdownMenuTrigger asChild>
            <button
              ref={ref}
              type="button"
              data-slot="multi-select-dropdown-trigger"
              className={cn(
                "flex min-w-[220px] items-center gap-2.5 rounded-full border border-border bg-card px-4 py-2.5 text-[13.5px] text-foreground",
                className
              )}
            >
              <span className="flex-1 overflow-hidden text-left text-ellipsis whitespace-nowrap">
                {values.length > 0 ? `${values.length} selected` : placeholder}
              </span>
              <ChevronDown
                className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")}
                aria-hidden="true"
              />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[240px]">
            {options.map((option) => {
              const checked = values.includes(option.value)
              return (
                <DropdownMenuCheckboxItem
                  key={option.value}
                  checked={checked}
                  onCheckedChange={(nextChecked) => toggleValue(option.value, nextChecked === true)}
                  onSelect={(event) => event.preventDefault()}
                >
                  {option.label}
                </DropdownMenuCheckboxItem>
              )
            })}
            <DropdownMenuSeparator />
            {/* Mockup's "Clear selection" row uses `--text-link`; this repo has
                no dedicated link token (see styles/index.css's note that
                `--nav-active` doubles as the link/primary-interactive color),
                so `text-nav-active` is the correct mapping here. */}
            <button
              type="button"
              data-slot="multi-select-dropdown-clear"
              onClick={() => onChange([])}
              className="w-full rounded-lg px-2.5 py-2 text-left text-[12.5px] text-nav-active hover:bg-muted"
            >
              Clear selection
            </button>
          </DropdownMenuContent>
        </DropdownMenu>
        {selectedOptions.length > 0 && (
          <div className="mt-3.5 flex flex-wrap gap-2">
            {selectedOptions.map((option) => (
              <Chip key={option.value} removable onRemove={() => removeValue(option.value)}>
                {option.label}
              </Chip>
            ))}
          </div>
        )}
      </div>
    )
  }
)
MultiSelectDropdown.displayName = "MultiSelectDropdown"

export { MultiSelectDropdown }
