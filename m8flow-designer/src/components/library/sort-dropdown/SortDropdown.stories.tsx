import * as React from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { SortDropdown } from "./SortDropdown"

const options = [
  { label: "Last run", value: "last-run" },
  { label: "Name", value: "name" },
  { label: "Status", value: "status" },
]

const meta = {
  title: "Library/SortDropdown",
  component: SortDropdown,
  args: {
    options,
    value: options[0].value,
    onChange: () => {},
  },
} satisfies Meta<typeof SortDropdown>

export default meta

type Story = StoryObj<typeof meta>

/**
 * Wraps the controlled `value`/`onChange` props in local state so the story
 * is actually interactive, without adding any state/coupling to the
 * component itself — same pattern as `library/search-bar`'s stories.
 */
function ControlledSortDropdown(props: React.ComponentProps<typeof SortDropdown>) {
  const [value, setValue] = React.useState(props.value)
  return <SortDropdown {...props} value={value} onChange={setValue} />
}

export const Default: Story = {
  render: (args) => <ControlledSortDropdown {...args} />,
}

export const NameSelected: Story = {
  render: (args) => <ControlledSortDropdown {...args} />,
  args: {
    value: "name",
  },
}

// Reuses the same pill-dropdown shape for a plain single-select filter
// (ticket 19) instead of the "Sort: " prefix — e.g. a Status filter.
const statusOptions = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Inactive", value: "inactive" },
]

export const NonSortLabel: Story = {
  name: 'Non-"Sort:" label (e.g. a Status filter)',
  render: (args) => <ControlledSortDropdown {...args} />,
  args: {
    options: statusOptions,
    value: statusOptions[1].value,
    label: "Status",
  },
}

// Counts render muted + right-aligned in the menu, never in the trigger.
export const WithCounts: Story = {
  render: (args) => <ControlledSortDropdown {...args} />,
  args: {
    label: "Status",
    options: [
      { label: "All", value: "all", count: 5 },
      { label: "Published", value: "published", count: 5 },
      { label: "Draft", value: "draft", count: 0 },
      { label: "Paused", value: "paused", count: 0 },
    ],
    value: "all",
  },
}

// Helper text for options that need explaining.
export const WithDescriptions: Story = {
  render: (args) => <ControlledSortDropdown {...args} />,
  args: {
    label: "Visibility",
    options: [
      { label: "Private", value: "PRIVATE", description: "Only you" },
      { label: "Tenant", value: "TENANT", description: "Everyone in this tenant" },
      { label: "Public", value: "PUBLIC", description: "Available to all tenants" },
    ],
    value: "PRIVATE",
  },
}
