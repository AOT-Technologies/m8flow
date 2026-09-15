import * as React from "react"
import { ChevronDown, X } from "lucide-react"

import { cn } from "@/lib/utils"

export interface ChipProps extends React.ComponentPropsWithoutRef<"button"> {
  /**
   * Sky-blue tinted "selected" look for the trailing-chevron filter chip
   * (mockup's "Any status" example, vs. the plain "All owners" / "Sort:
   * last run" chips). Has no visual effect when `removable` is set — a
   * removable chip already renders with its own always-on tinted
   * background (the mockup's "selected filter chip" pattern).
   */
  active?: boolean
  /**
   * Renders the "selected filter chip" pattern instead of the default
   * filter-chip pattern: a trailing `X` button in place of the chevron,
   * for tags added via a multi-select (see ticket 07's
   * `MultiSelectDropdown`). The chip root becomes a non-interactive
   * `<span>` — only the trailing `X` is a real `<button>` — matching the
   * mockup, which never nests a `<button>` inside a `<button>`. Pass
   * `onRemove` to handle the `X` click; the forwarded `ref` attaches to
   * that inner remove button in this mode (so `ref` always resolves to a
   * real `HTMLButtonElement` regardless of `removable`).
   */
  removable?: boolean
  /** Called when the trailing `X` is clicked. Only relevant when `removable`. */
  onRemove?: (event: React.MouseEvent<HTMLButtonElement>) => void
  /** Accessible label for the trailing remove button. Defaults to `"Remove"`. */
  removeLabel?: string
  /**
   * Visually-present, non-interactive "inert" chip — matches the mockup's
   * "Any status"/"All owners" placeholder filter chips (chrome that exists
   * but isn't wired to a real dropdown yet). Uses `aria-disabled` (not the
   * native `disabled` attribute) so the chip stays focusable/discoverable,
   * matching what both confirmed call sites already did by hand before this
   * prop existed. Suppresses `onClick` while set. Takes priority over
   * `removable` — an inert chip has nothing to remove, so a disabled chip
   * always renders the plain filter shape (chevron, not `X`) regardless of
   * `removable`.
   */
  disabled?: boolean
}

const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
  (
    {
      className,
      active,
      removable = false,
      onRemove,
      removeLabel = "Remove",
      disabled = false,
      children,
      ...rest
    },
    ref
  ) => {
    if (removable && !disabled) {
      return (
        <span
          data-slot="chip"
          data-variant="removable"
          className={cn(
            "inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full bg-nav-active/14 px-2.5 py-1 text-[12.5px] leading-none font-medium text-foreground whitespace-nowrap",
            className
          )}
          {...rest}
        >
          {children}
          <button
            ref={ref}
            type="button"
            onClick={onRemove}
            aria-label={removeLabel}
            data-slot="chip-remove"
            className="inline-flex shrink-0 items-center justify-center text-foreground/70 transition-colors hover:text-foreground"
          >
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </span>
      )
    }

    // Pulled out separately (rather than destructured at the top, alongside
    // `disabled`) so the `removable && !disabled` branch above still spreads
    // its own `onClick` from `rest` unchanged — only this inert/filter shape
    // needs to conditionally suppress it.
    const { onClick, ...filterRest } = rest

    return (
      <button
        ref={ref}
        type="button"
        data-slot="chip"
        data-variant="filter"
        data-active={active ? "true" : undefined}
        data-disabled={disabled ? "true" : undefined}
        aria-disabled={disabled ? "true" : undefined}
        onClick={disabled ? undefined : onClick}
        className={cn(
          "inline-flex w-fit shrink-0 items-center gap-[7px] rounded-full border px-3.5 py-2 text-[13.5px] leading-none font-medium whitespace-nowrap",
          disabled
            ? "cursor-default border-border bg-card text-muted-foreground select-none"
            : active
              ? "border-nav-active bg-nav-active/10 text-foreground"
              : "border-border bg-card text-foreground hover:bg-muted",
          className
        )}
        {...filterRest}
      >
        {children}
        <ChevronDown className="size-[13px] shrink-0" aria-hidden="true" />
      </button>
    )
  }
)
Chip.displayName = "Chip"

export { Chip }
