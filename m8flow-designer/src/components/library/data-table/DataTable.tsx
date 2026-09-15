import * as React from "react"

import { cn } from "@/lib/utils"

export interface DataTableColumn<T> {
  /** Stable identity for the column (React key, not a lookup into `T`). */
  key: string
  header: React.ReactNode
  /**
   * How to render this column's cell for a given row. Fully generic — a
   * "status" column is just a column whose `render` happens to return a
   * `Pill`; there is no special "type: pill" column kind to learn.
   */
  render?: (row: T) => React.ReactNode
  className?: string
  /**
   * CSS grid track size for this column (e.g. `"minmax(220px,2.4fr)"` or
   * `"120px"`), passed straight into the shared `grid-template-columns`
   * used by both the header row and every data row. Defaults to
   * `"minmax(0,1fr)"` — an even split — when omitted.
   */
  width?: string
}

export interface DataTableProps<T>
  extends Omit<React.ComponentProps<"div">, "children"> {
  columns: DataTableColumn<T>[]
  rows: T[]
  /** Defaults to the row's array index when omitted. */
  getRowKey?: (row: T, index: number) => string | number
  /** Rendered in place of the row list when `rows` is empty. */
  emptyState?: React.ReactNode
  /**
   * Minimum width of the scrollable grid content, so narrow viewports get a
   * horizontal scrollbar (via the outer `overflow-x-auto`) instead of a
   * squashed/wrapped layout. Defaults to `"640px"`, matching the mockup.
   */
  minWidth?: string
  /**
   * Makes every row clickable — the "click anywhere in the row to open it"
   * pattern `process-instances`/`processes`/`task-review` each hand-rolled
   * independently before this (component-adoption map, ticket 23). When
   * provided, each row gets `role="button"`, `tabIndex={0}`, a pointer
   * cursor, and Enter/Space activates it the same as a click — mirroring
   * those hand-rolled implementations exactly. Omit entirely for a plain,
   * non-interactive `role="row"` (today's unchanged default).
   *
   * A row's own interactive cells (buttons, links, an `ActionMenu`) are
   * *not* handled here — same as every existing consumer, wrap that cell's
   * content in its own `onClick`/`onKeyDown` that calls
   * `event.stopPropagation()` so it doesn't also fire the row click. This
   * stays the column's `render` function's job, not `DataTable`'s, so the
   * common case (no nested interactive cells) doesn't pay for it.
   */
  onRowClick?: (row: T, index: number) => void
}

/**
 * Generic columns/rows table, grid-based (not a native `<table>`) to match
 * the mockup's layout exactly — a shared `grid-template-columns` (built from
 * each column's `width`) is applied to the header row and every data row so
 * columns line up.
 *
 * Deliberately knows nothing about "process model / status / runs / last
 * run" — that's example data for the Storybook story, not this component.
 * Kept in its own module, independent of `Pagination`, so a consumer that
 * only needs one of the two only pulls in that one.
 */
function DataTable<T>({
  columns,
  rows,
  getRowKey,
  emptyState,
  minWidth = "640px",
  onRowClick,
  className,
  ...props
}: DataTableProps<T>) {
  const gridTemplateColumns = columns.map((column) => column.width ?? "minmax(0,1fr)").join(" ")

  return (
    <div
      data-slot="data-table"
      role="table"
      className={cn("w-full overflow-x-auto", className)}
      {...props}
    >
      <div style={{ minWidth }}>
        <div
          data-slot="data-table-header"
          role="row"
          className="grid gap-4 border-y border-border bg-muted px-7 py-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase"
          style={{ gridTemplateColumns }}
        >
          {columns.map((column) => (
            <div key={column.key} role="columnheader" className={column.className}>
              {column.header}
            </div>
          ))}
        </div>

        {rows.length === 0 ? (
          <div
            data-slot="data-table-empty"
            className="bg-card px-7 py-6 text-sm text-muted-foreground"
          >
            {emptyState ?? "No data"}
          </div>
        ) : (
          rows.map((row, index) => (
            <div
              key={getRowKey ? getRowKey(row, index) : index}
              data-slot="data-table-row"
              role={onRowClick ? "button" : "row"}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row, index) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault()
                        onRowClick(row, index)
                      }
                    }
                  : undefined
              }
              className={cn(
                "grid items-center gap-4 border-b border-border bg-card px-7 py-3.5",
                onRowClick && "cursor-pointer"
              )}
              style={{ gridTemplateColumns }}
            >
              {columns.map((column) => (
                <div key={column.key} role="cell" className={column.className}>
                  {column.render
                    ? column.render(row)
                    : ((row as Record<string, unknown>)[column.key] as React.ReactNode)}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export { DataTable }
