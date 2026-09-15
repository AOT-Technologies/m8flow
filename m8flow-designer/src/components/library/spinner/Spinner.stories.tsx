import type { Meta, StoryObj } from "@storybook/react-vite"

import { Spinner } from "./Spinner"

const meta: Meta<typeof Spinner> = {
  title: "Library/Spinner",
  component: Spinner,
  parameters: {
    layout: "centered",
  },
  args: {
    size: 16,
  },
  argTypes: {
    size: {
      control: { type: "number", min: 12, max: 48, step: 2 },
    },
  },
}

export default meta

type Story = StoryObj<typeof Spinner>

// The mockup's exact "Loading spinner" example: a 16px ring next to a label.
export const Default: Story = {
  render: (args) => (
    <div className="flex items-center gap-2.5">
      <Spinner {...args} />
      <span className="text-[13.5px] text-muted-foreground">Loading spinner</span>
    </div>
  ),
}

export const Sizes: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <Spinner size={16} />
      <Spinner size={24} />
      <Spinner size={32} />
    </div>
  ),
}
