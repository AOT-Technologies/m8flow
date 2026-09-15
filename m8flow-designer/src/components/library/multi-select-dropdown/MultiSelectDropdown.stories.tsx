import * as React from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { MultiSelectDropdown } from "./MultiSelectDropdown"

const options = [
  { label: "Published", value: "published" },
  { label: "Draft", value: "draft" },
  { label: "Paused", value: "paused" },
  { label: "Needs attention", value: "needs-attention" },
]

const meta = {
  title: "Library/MultiSelectDropdown",
  component: MultiSelectDropdown,
  args: {
    options,
    values: [],
    onChange: () => {},
    placeholder: "Filter by status",
  },
} satisfies Meta<typeof MultiSelectDropdown>

export default meta

type Story = StoryObj<typeof meta>

/**
 * Wraps the controlled `values`/`onChange` props in local state so the
 * story is actually interactive, without adding any state/coupling to the
 * component itself — same pattern as `library/search-bar`'s stories.
 */
function ControlledMultiSelectDropdown(
  props: React.ComponentProps<typeof MultiSelectDropdown>
) {
  const [values, setValues] = React.useState(props.values)
  return <MultiSelectDropdown {...props} values={values} onChange={setValues} />
}

export const EmptyPlaceholder: Story = {
  render: (args) => <ControlledMultiSelectDropdown {...args} />,
}

export const WithSelections: Story = {
  render: (args) => <ControlledMultiSelectDropdown {...args} />,
  args: {
    values: ["published", "draft"],
  },
}
