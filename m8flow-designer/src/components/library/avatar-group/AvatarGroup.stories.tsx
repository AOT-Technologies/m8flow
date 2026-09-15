import type { Meta, StoryObj } from "@storybook/react-vite"

import { AvatarGroup } from "./AvatarGroup"

const meta = {
  title: "Library/AvatarGroup",
  component: AvatarGroup,
  parameters: {
    layout: "centered",
  },
} satisfies Meta<typeof AvatarGroup>

export default meta

type Story = StoryObj<typeof meta>

/** The mockup's two-avatar overlapping stack: no overflow, `max` unset. */
export const Stack: Story = {
  args: {
    items: [
      { initials: "RS", className: "bg-foreground text-white" },
      { initials: "AN", className: "bg-nav-active text-foreground" },
    ],
  },
}

/**
 * The mockup's exact "+3" overflow example — five members, `max={1}` so
 * only "RS" shows before the trailing overflow avatar.
 */
export const WithOverflow: Story = {
  args: {
    items: [
      { initials: "RS", className: "bg-foreground text-white" },
      { initials: "JM", className: "bg-primary text-white" },
      { initials: "AN", className: "bg-nav-active text-foreground" },
      { initials: "PT" },
    ],
    max: 1,
  },
}

export const CustomOverflowColor: Story = {
  args: {
    items: [
      { initials: "RS", className: "bg-foreground text-white" },
      { initials: "JM", className: "bg-primary text-white" },
      { initials: "AN", className: "bg-nav-active text-foreground" },
    ],
    max: 1,
    overflowClassName: "bg-primary text-white",
  },
}

export const MediumSize: Story = {
  args: {
    items: [
      { initials: "RS", className: "bg-foreground text-white" },
      { initials: "JM", className: "bg-primary text-white" },
      { initials: "AN", className: "bg-nav-active text-foreground" },
    ],
    max: 2,
    size: "md",
  },
}
