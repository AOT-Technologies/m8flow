import type { Meta, StoryObj } from "@storybook/react-vite"

import { Pill } from "./Pill"

const meta: Meta<typeof Pill> = {
  title: "Library/Pill",
  component: Pill,
  parameters: {
    layout: "centered",
  },
  args: {
    tone: "success",
    dot: true,
    children: "Published",
  },
  argTypes: {
    tone: {
      control: "select",
      options: ["success", "error", "warning", "muted", "info"],
    },
  },
}

export default meta

type Story = StoryObj<typeof Pill>

// The mockup's four status-dot pill examples, one per tone.
export const Success: Story = {
  args: { tone: "success", children: "Published" },
}

export const Error: Story = {
  args: { tone: "error", children: "Needs attention" },
}

export const Warning: Story = {
  args: { tone: "warning", children: "Paused" },
}

export const Muted: Story = {
  args: { tone: "muted", children: "Draft" },
}

// Added alongside the other four when `Pill` gained an `info` tone —
// matches `ui/badge.tsx`'s own `info` variant and `library/alert`'s `info`
// tone (`bg-info/10 text-info`), for pages that today reach for
// `Badge variant="info"` instead of `Pill`.
export const Info: Story = {
  args: { tone: "info", children: "In review" },
}

export const AllStatusTones: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2.5">
      <Pill tone="success">Published</Pill>
      <Pill tone="error">Needs attention</Pill>
      <Pill tone="warning">Paused</Pill>
      <Pill tone="muted">Draft</Pill>
      <Pill tone="info">In review</Pill>
    </div>
  ),
}

// The mockup's plain static tag pill pattern: same visual family, no dot,
// no status meaning.
export const PlainTag: Story = {
  name: "Plain tag (dot={false})",
  args: { dot: false, tone: "muted", children: "Ticketmaster API" },
}

export const PlainTags: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Pill dot={false}>Ticketmaster API</Pill>
      <Pill dot={false}>Spotify OAuth</Pill>
    </div>
  ),
}
