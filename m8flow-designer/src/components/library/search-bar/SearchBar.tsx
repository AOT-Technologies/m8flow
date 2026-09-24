import * as React from "react"
import { Search } from "lucide-react"

import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"

export interface SearchBarProps
  extends Omit<
    React.ComponentProps<"input">,
    "value" | "onChange" | "size" | "className"
  > {
  /** Controlled input value. */
  value: string
  /**
   * Receives the raw string value (matches this app's existing
   * `onSearchChange`/`setSearch` convention — see
   * ProcessInstancesList/TemplatesGalleryList/ProcessesModelsList — rather
   * than the underlying DOM change event.
   */
  onChange: (value: string) => void
  /**
   * `page` = sits directly on a page/card surface (`--card`, matches the
   * mockup's "Search bar" default pill). `sunken` = sits on a sunken/gray
   * surface such as inside a modal (`--muted`), matching the mockup's
   * "Sunken variant, e.g. for modal search" example.
   */
  variant?: "page" | "sunken"
  className?: string
  /** Classes applied to the underlying `Input` element itself. */
  inputClassName?: string
}

/**
 * Pill-shaped search input (leading search icon), composed on top of
 * `ui/input.tsx` per the map's decision to build on existing `ui/`
 * primitives rather than duplicate them. Purely presentational/controlled:
 * no internal fetch/router coupling, and no keyboard-shortcut hint —
 * pages that bind ⌘K do so themselves, and most screens using this bar
 * don't, so the badge only ever misinformed.
 */
const SearchBar = React.forwardRef<HTMLInputElement, SearchBarProps>(
  (
    { value, onChange, variant = "page", placeholder, className, inputClassName, ...props },
    ref
  ) => {
    return (
      <div
        data-slot="search-bar"
        data-variant={variant}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-full border border-border px-4 py-2.5",
          variant === "sunken" ? "bg-muted" : "bg-card",
          className
        )}
      >
        <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <Input
          ref={ref}
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className={cn(
            "h-auto flex-1 border-0 bg-transparent p-0 text-[13.5px] shadow-none focus-visible:border-transparent focus-visible:ring-0",
            inputClassName
          )}
          {...props}
        />
      </div>
    )
  }
)
SearchBar.displayName = "SearchBar"

export { SearchBar }
