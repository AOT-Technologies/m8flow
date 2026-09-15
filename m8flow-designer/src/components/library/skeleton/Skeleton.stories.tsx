import type { Meta, StoryObj } from "@storybook/react-vite"

import { Skeleton } from "./Skeleton"

const meta: Meta<typeof Skeleton> = {
  title: "Library/Skeleton",
  component: Skeleton,
  args: {
    width: "70%",
    height: 14,
  },
}

export default meta

type Story = StoryObj<typeof Skeleton>

export const Default: Story = {}

// The mockup's exact three-bar example: 70% / 100% / 45% widths stacked.
export const TextBlock: Story = {
  render: () => (
    <div className="flex max-w-[420px] flex-col gap-2.5">
      <Skeleton width="70%" />
      <Skeleton width="100%" />
      <Skeleton width="45%" />
    </div>
  ),
}

export const CustomSize: Story = {
  args: { width: 200, height: 40 },
}
