import * as React from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { Pill } from "@/components/library/pill/Pill"
import { Pagination } from "@/components/library/pagination/Pagination"
import { DataTable, type DataTableColumn } from "./DataTable"

// A deliberately non-"process model" shaped example, to make clear the
// component itself carries no domain-specific column knowledge — genericity
// is proven by using it for something the mockup never mentions.
interface Teammate {
  id: string
  name: string
  email: string
  role: string
}

const teammates: Teammate[] = [
  { id: "1", name: "Priya Shah", email: "priya@example.com", role: "Admin" },
  { id: "2", name: "Marcus Lee", email: "marcus@example.com", role: "Editor" },
  { id: "3", name: "Sofia Ruiz", email: "sofia@example.com", role: "Reviewer" },
]

const teammateColumns: DataTableColumn<Teammate>[] = [
  { key: "name", header: "Name" },
  { key: "email", header: "Email" },
  { key: "role", header: "Role" },
]

// `DataTable` is a generic component, so `typeof DataTable` alone can't tell
// Storybook's `Meta<>` what `T` is (it'd default to `unknown` and reject
// `Teammate`-shaped `args`). Pinning `T` via a TS 4.7+ instantiation
// expression (`DataTable<Teammate>`) gives `meta`/`StoryObj` a concrete,
// correctly-typed component to check `args` against.
const TeammateDataTable = DataTable<Teammate>

const meta = {
  title: "Library/DataTable",
  component: TeammateDataTable,
  args: {
    columns: teammateColumns,
    rows: teammates,
  },
} satisfies Meta<typeof TeammateDataTable>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Empty: Story = {
  args: {
    rows: [],
    emptyState: "No teammates yet.",
  },
}

// The "click anywhere in the row to open it" pattern `process-instances`/
// `processes`/`task-review` each hand-rolled independently before this
// (component-adoption map, ticket 23) — opt in via `onRowClick`.
export const ClickableRows: Story = {
  args: {
    onRowClick: (row) => window.alert(`Opened ${row.name}`),
  },
}

// --- Combined story: reproduces the mockup's "Table with pagination"
// section (Process model / Status / Runs 30d / Last run), composing
// `DataTable` with the independent `Pagination` component. This example
// data — including the status-column `render` returning a `Pill` — lives
// here, not inside either component: `DataTable` has no idea what a
// "process model" or a "status" is, it just calls each column's `render`.

interface ProcessModelRow {
  id: string
  name: string
  status: "success" | "error" | "warning" | "muted"
  statusLabel: string
  runs30d: number
  lastRun: string
}

const processModels: ProcessModelRow[] = [
  { id: "1", name: "Invoice approval", status: "success", statusLabel: "Published", runs30d: 128, lastRun: "2h ago" },
  { id: "2", name: "Employee onboarding", status: "success", statusLabel: "Published", runs30d: 64, lastRun: "5h ago" },
  { id: "3", name: "Expense reimbursement", status: "warning", statusLabel: "Paused", runs30d: 12, lastRun: "1d ago" },
  { id: "4", name: "Vendor contract review", status: "error", statusLabel: "Needs attention", runs30d: 3, lastRun: "3d ago" },
  { id: "5", name: "Customer refund request", status: "muted", statusLabel: "Draft", runs30d: 0, lastRun: "—" },
  { id: "6", name: "PTO request", status: "success", statusLabel: "Published", runs30d: 211, lastRun: "12m ago" },
  { id: "7", name: "IT access request", status: "success", statusLabel: "Published", runs30d: 47, lastRun: "1h ago" },
  { id: "8", name: "Purchase order approval", status: "warning", statusLabel: "Paused", runs30d: 9, lastRun: "2d ago" },
  { id: "9", name: "Change request review", status: "muted", statusLabel: "Draft", runs30d: 0, lastRun: "—" },
  { id: "10", name: "Incident postmortem", status: "success", statusLabel: "Published", runs30d: 18, lastRun: "6h ago" },
  { id: "11", name: "New hire equipment request", status: "error", statusLabel: "Needs attention", runs30d: 2, lastRun: "4d ago" },
]

const processModelColumns: DataTableColumn<ProcessModelRow>[] = [
  { key: "name", header: "Process model", width: "minmax(220px,2.4fr)" },
  {
    key: "status",
    header: "Status",
    width: "minmax(0,140px)",
    render: (row) => <Pill tone={row.status}>{row.statusLabel}</Pill>,
  },
  {
    key: "runs30d",
    header: "Runs 30d",
    width: "minmax(0,90px)",
    className: "font-mono text-[13px] text-muted-foreground",
  },
  {
    key: "lastRun",
    header: "Last run",
    width: "minmax(0,130px)",
    className: "text-[13px] whitespace-nowrap text-muted-foreground",
  },
]

const PAGE_SIZE = 5

function TableWithPagination() {
  const [page, setPage] = React.useState(1)
  const pageRows = processModels.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div className="flex flex-col gap-3">
      <DataTable columns={processModelColumns} rows={pageRows} getRowKey={(row) => row.id} />
      <Pagination
        page={page}
        onPageChange={setPage}
        totalItems={processModels.length}
        pageSize={PAGE_SIZE}
        className="px-7"
      />
    </div>
  )
}

export const WithPagination: Story = {
  name: "Table with pagination (mockup)",
  render: () => <TableWithPagination />,
}
