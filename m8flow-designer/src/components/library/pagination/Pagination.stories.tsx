import * as React from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { Pagination, type PaginationCountedProps } from "./Pagination"

// Storybook's `Meta`/`StoryObj` machinery doesn't resolve a discriminated
// union prop type cleanly — `args` ends up typed against an intersection
// where the counted-mode fields (`totalItems`/`pageSize`) collapse to
// `never`, since `Pagination` also accepts the unrelated `hasMore`-mode
// shape. Same class of issue as `DataTable.stories.tsx`'s own generic-
// component workaround (there for a type *parameter*, here for a type
// *union*): pin `meta` to the counted-mode variant explicitly. The
// `hasMore`-mode story below (`HasMoreMode`) bypasses `args`/`Story` typing
// entirely and renders directly instead, so it isn't affected by this.
const CountedPagination = Pagination as React.ForwardRefExoticComponent<
  PaginationCountedProps & React.RefAttributes<HTMLElement>
>

const meta = {
  title: "Library/Pagination",
  component: CountedPagination,
  // Layout centering (both axes) comes from the global default in
  // .storybook/preview.ts. Pagination's root is a `justify-between` <nav>
  // meant to span whatever real container it sits in (a table footer) —
  // that's intentional, not a bug, but it means the *component* still needs
  // an explicit width or it just shrinks to its tightest content fit inside
  // Storybook's centered canvas. This decorator gives it a realistic width
  // (matching the mockup's own table width, `min-width:640px` in
  // DataTable.stories.tsx) so the range label and pager buttons show
  // genuinely spread apart, the way they do at the bottom of a normal-sized
  // table — the centered layout then centers that whole bounded box.
  //
  // Deliberately `w-[640px]` (fixed), not `max-w-[640px]`: a max-width is
  // only an upper bound, and nothing in the chain up to Storybook's
  // shrink-to-fit "centered" canvas has a definite width for it to apply
  // against, so `max-w` alone still collapsed to content size — confirmed
  // by measuring the rendered box (239px, not 640px) after the first
  // attempt, not just by eyeballing the screenshot.
  decorators: [
    (Story) => (
      <div className="w-[640px]">
        <Story />
      </div>
    ),
  ],
  // Every story below supplies its own via `ControlledPagination` wrapping
  // `page`/`onPageChange` in local state — this default only exists to
  // satisfy the type of `args` before `render` swaps it out.
  args: {
    onPageChange: () => {},
  },
} satisfies Meta<typeof CountedPagination>

export default meta

type Story = StoryObj<typeof meta>

/**
 * Wraps the controlled `page`/`onPageChange` props in local state so the
 * story is actually interactive, without adding any state to the component
 * itself.
 */
function ControlledPagination(props: React.ComponentProps<typeof CountedPagination>) {
  const [page, setPage] = React.useState(props.page)
  return <CountedPagination {...props} page={page} onPageChange={setPage} />
}

export const Default: Story = {
  render: (args) => <ControlledPagination {...args} />,
  args: {
    page: 1,
    totalItems: 11,
    pageSize: 5,
  },
}

export const MiddlePage: Story = {
  name: "Middle page (both buttons enabled)",
  render: (args) => <ControlledPagination {...args} />,
  args: {
    page: 2,
    totalItems: 11,
    pageSize: 5,
  },
}

export const LastPage: Story = {
  name: "Last page (next disabled, partial range)",
  render: (args) => <ControlledPagination {...args} />,
  args: {
    page: 3,
    totalItems: 11,
    pageSize: 5,
  },
}

export const SinglePage: Story = {
  name: "Single page (both prev/next disabled)",
  render: (args) => <ControlledPagination {...args} />,
  args: {
    page: 1,
    totalItems: 4,
    pageSize: 5,
  },
}

export const Truncated: Story = {
  name: "Truncated (many pages, ellipsis on both sides)",
  render: (args) => <ControlledPagination {...args} />,
  args: {
    page: 12,
    totalItems: 200,
    pageSize: 5,
  },
}

export const WithRowsPerPage: Story = {
  name: "With rows-per-page selector",
  // `render` ignores `args` entirely and drives its own local state — these
  // values only exist to satisfy `Story`'s required `args` shape (same
  // reasoning as `meta.args`'s own comment above).
  args: {
    page: 1,
    totalItems: 42,
    pageSize: 5,
  },
  render: () => {
    function ControlledWithPageSize() {
      const [page, setPage] = React.useState(1)
      const [pageSize, setPageSize] = React.useState(5)
      return (
        <CountedPagination
          page={page}
          onPageChange={setPage}
          totalItems={42}
          pageSize={pageSize}
          pageSizeOptions={[5, 10, 25]}
          onPageSizeChange={(nextSize) => {
            setPageSize(nextSize)
            setPage(1)
          }}
        />
      )
    }
    return <ControlledWithPageSize />
  },
}

/**
 * `hasMore`-only mode — for backends that return `{ has_more }` with no
 * total count (e.g. `tenant-management`'s member/group lists). No numbered
 * buttons or range label; just Previous/Next and a plain "Page N" label.
 * Bypasses `args`/`Story` typing entirely (see the `CountedPagination`
 * comment above) since this is the other half of `Pagination`'s
 * discriminated union, not the counted mode `meta` is pinned to.
 */
export const HasMoreMode: Story = {
  name: "hasMore mode (no total count)",
  // `render` ignores `args` and drives its own local state via the real
  // `Pagination` component in its other (`hasMore`) mode — these values only
  // exist to satisfy `Story`'s required `args` shape.
  args: {
    page: 1,
    totalItems: 0,
    pageSize: 5,
  },
  render: () => {
    function ControlledHasMore() {
      const [page, setPage] = React.useState(1)
      const hasMore = page < 4
      return <Pagination page={page} onPageChange={setPage} hasMore={hasMore} />
    }
    return <ControlledHasMore />
  },
}
