import type { Meta, StoryObj } from "@storybook/react-vite"

import { Chip } from "./Chip"

const meta: Meta<typeof Chip> = {
  title: "Library/Chip",
  component: Chip,
  parameters: {
    layout: "centered",
  },
  args: {
    children: "Any status",
  },
}

export default meta

type Story = StoryObj<typeof Chip>

// Mockup's inactive filter chip pattern (e.g. "All owners", "Sort: last
// run"): plain card background, default border.
export const FilterChipInactive: Story = {
  args: { children: "All owners" },
}

// Mockup's active/selected filter chip pattern (e.g. "Any status"):
// sky-blue tinted background + border.
export const FilterChipActive: Story = {
  args: { children: "Any status", active: true },
}

export const FilterChips: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Chip active>Any status</Chip>
      <Chip>All owners</Chip>
      <Chip>Sort: last run</Chip>
    </div>
  ),
}

// Mockup's "selected filter chip" pattern (used later by ticket 07's
// MultiSelectDropdown): trailing X instead of a chevron.
export const Removable: Story = {
  args: {
    children: "Marketing",
    removable: true,
    onRemove: () => {},
  },
}

export const RemovableChips: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Chip removable onRemove={() => {}}>
        Marketing
      </Chip>
      <Chip removable onRemove={() => {}}>
        Ops
      </Chip>
      <Chip removable onRemove={() => {}}>
        Finance
      </Chip>
    </div>
  ),
}

// Visually-present, non-interactive "inert" chip (`processes`/`templates`
// page adoption, ticket 20) — a filter chip that exists as chrome but isn't
// wired to a real dropdown yet.
export const Disabled: Story = {
  args: { children: 'Any status', disabled: true, onClick: () => {} },
}
