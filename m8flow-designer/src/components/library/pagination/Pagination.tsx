import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"

type PaginationBaseProps = Omit<React.ComponentProps<"nav">, "onChange"> & {
  /**
   * Current page, 1-indexed. Not required to already be in `[1, totalPages]`
   * — e.g. a caller may still be showing `page={4}` for a moment after
   * `totalItems` shrinks under it. Clamped internally for display/disabled
   * state so that transient case never renders a blank/out-of-range page.
   */
  page: number
  /**
   * Called with the next 1-indexed page number when the prev/next button or
   * a page number button is activated. Never called for the already-current
   * page, or past the first/last page (those buttons are `disabled`).
   */
  onPageChange: (page: number) => void
}

export interface PaginationCountedProps extends PaginationBaseProps {
  /** Total item count — enables numbered page buttons and the "x–y of z" range label. */
  totalItems: number
  pageSize: number
  hasMore?: never
  /**
   * Optional "Rows per page" selector shown beside the range label. Provide
   * both together or neither — only meaningful in the total-driven (counted)
   * mode, since a `hasMore`-only backend usually can't tell you how a page
   * size change affects a cursor it doesn't expose a count for.
   */
  pageSizeOptions?: number[]
  onPageSizeChange?: (pageSize: number) => void
}

export interface PaginationHasMoreProps extends PaginationBaseProps {
  /**
   * `hasMore`-only mode, for backends that only return `{ has_more }` (no
   * total count, sometimes not even a page count) — e.g.
   * `tenant-management`'s member/group lists, `configuration/SecretListPage`.
   * No numbered buttons or range label (there's nothing to compute them
   * from); just Previous/Next plus a plain "Page N" label. `Previous` is
   * disabled at `page <= 1`; `Next` is disabled when `hasMore` is `false`.
   */
  hasMore: boolean
  totalItems?: never
  pageSize?: never
  pageSizeOptions?: never
  onPageSizeChange?: never
}

export type PaginationProps = PaginationCountedProps | PaginationHasMoreProps

function isCountedProps(props: PaginationProps): props is PaginationCountedProps {
  return typeof props.totalItems === "number"
}

/**
 * Collapses a numbered page-button row down to first, last, current ± 1,
 * with an `"ellipsis"` marker filling any gap — the standard truncation
 * pattern, needed once `totalPages` gets large (e.g. `task-review`'s inbox,
 * which can run into the hundreds). Small page counts (`<= 7`, enough room
 * for first + last + current ± 1 + up to two more without a gap) render
 * every page, unchanged from the original one-button-per-page behavior.
 */
function buildPageWindow(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const keep = new Set<number>([1, total, current])
  if (current - 1 >= 1) keep.add(current - 1)
  if (current + 1 <= total) keep.add(current + 1)

  const sorted = Array.from(keep).sort((a, b) => a - b)
  const result: (number | "ellipsis")[] = []
  sorted.forEach((pageNumber, index) => {
    if (index > 0 && pageNumber - sorted[index - 1] > 1) {
      result.push("ellipsis")
    }
    result.push(pageNumber)
  })
  return result
}

const navButtonClassName =
  "flex size-[30px] shrink-0 items-center justify-center rounded-full border border-border text-foreground disabled:pointer-events-none disabled:opacity-40"

/**
 * Prev/next round icon buttons + (in counted mode) numbered page buttons and
 * an "x–y of z" range label, per the mockup's table pager. Page count is
 * derived from `totalItems`/`pageSize` internally — callers never compute it
 * themselves.
 *
 * Two modes, chosen by which props are passed (see `PaginationCountedProps`/
 * `PaginationHasMoreProps`): the original total-driven mode, or a
 * `hasMore`-only mode for backends that don't expose a total count.
 *
 * Kept in its own module, independent of `DataTable`, so a consumer that
 * paginates something other than a `DataTable` (or vice versa) only pulls in
 * the piece it needs.
 */
const Pagination = React.forwardRef<HTMLElement, PaginationProps>((props, ref) => {
  const { page, onPageChange, className, ...rest } = props

  if (isCountedProps(props)) {
    const { totalItems, pageSize, pageSizeOptions, onPageSizeChange, ...navProps } =
      rest as Omit<PaginationCountedProps, "page" | "onPageChange" | "className">
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
    const currentPage = Math.min(Math.max(page, 1), totalPages)

    const rangeStart = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1
    const rangeEnd = Math.min(currentPage * pageSize, totalItems)

    const goTo = (target: number) => {
      if (target === currentPage || target < 1 || target > totalPages) return
      onPageChange(target)
    }

    const pageItems = buildPageWindow(currentPage, totalPages)

    return (
      <nav
        ref={ref}
        data-slot="pagination"
        aria-label="Pagination"
        className={cn("flex items-center justify-between gap-4", className)}
        {...navProps}
      >
        <div className="flex items-center gap-4">
          <span data-slot="pagination-range" className="text-[13px] text-muted-foreground">
            {rangeStart}–{rangeEnd} of {totalItems}
          </span>

          {pageSizeOptions && onPageSizeChange ? (
            <label
              data-slot="pagination-page-size"
              className="flex items-center gap-1.5 text-[13px] text-muted-foreground"
            >
              Rows per page
              <select
                value={pageSize}
                onChange={(event) => onPageSizeChange(Number(event.target.value))}
                className="rounded-md border border-border bg-card px-1.5 py-1 text-[13px] text-foreground"
              >
                {pageSizeOptions.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-slot="pagination-prev"
            aria-label="Previous page"
            disabled={currentPage === 1}
            onClick={() => goTo(currentPage - 1)}
            className={navButtonClassName}
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </button>

          {pageItems.map((item, index) =>
            item === "ellipsis" ? (
              <span
                // Two possible gaps (before/after the current-page cluster),
                // never more — index-based key is safe and stable here.
                key={`ellipsis-${index}`}
                aria-hidden="true"
                className="flex h-[30px] min-w-[20px] shrink-0 items-center justify-center text-[12.5px] text-muted-foreground"
              >
                …
              </span>
            ) : (
              <button
                key={item}
                type="button"
                data-slot="pagination-page"
                aria-label={`Page ${item}`}
                aria-current={item === currentPage ? "page" : undefined}
                onClick={() => goTo(item)}
                className={cn(
                  "flex h-[30px] min-w-[30px] shrink-0 items-center justify-center rounded-full px-1.5 font-mono text-[12.5px]",
                  // Mockup: current page gets a solid foreground/white treatment,
                  // matching `ui/button.tsx`'s `pill-dark` variant's own
                  // `bg-foreground` + `text-white` pairing rather than inventing
                  // a new token for "white text on dark fill".
                  item === currentPage
                    ? "bg-foreground text-white"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                {item}
              </button>
            )
          )}

          <button
            type="button"
            data-slot="pagination-next"
            aria-label="Next page"
            disabled={currentPage === totalPages}
            onClick={() => goTo(currentPage + 1)}
            className={navButtonClassName}
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </button>
        </div>
      </nav>
    )
  }

  const { hasMore, ...navProps } = rest as Omit<
    PaginationHasMoreProps,
    "page" | "onPageChange" | "className"
  >
  const currentPage = Math.max(page, 1)

  return (
    <nav
      ref={ref}
      data-slot="pagination"
      data-mode="has-more"
      aria-label="Pagination"
      className={cn("flex items-center justify-between gap-4", className)}
      {...navProps}
    >
      <span data-slot="pagination-range" className="text-[13px] text-muted-foreground">
        Page {currentPage}
      </span>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          data-slot="pagination-prev"
          aria-label="Previous page"
          disabled={currentPage <= 1}
          onClick={() => currentPage > 1 && onPageChange(currentPage - 1)}
          className={navButtonClassName}
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          data-slot="pagination-next"
          aria-label="Next page"
          disabled={!hasMore}
          onClick={() => hasMore && onPageChange(currentPage + 1)}
          className={navButtonClassName}
        >
          <ChevronRight className="size-4" aria-hidden="true" />
        </button>
      </div>
    </nav>
  )
})
Pagination.displayName = "Pagination"

export { Pagination, buildPageWindow }
