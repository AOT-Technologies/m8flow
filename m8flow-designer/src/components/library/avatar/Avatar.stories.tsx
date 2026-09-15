import type { Meta, StoryObj } from "@storybook/react-vite"

import { Avatar, AvatarFallback } from "./Avatar"

/**
 * `library/avatar` is a pure re-export of `ui/avatar.tsx` — see the
 * comment in `Avatar.tsx`. These stories exist to document the mockup's
 * three solo-avatar examples (per-instance background/text colors, not
 * baked into the component itself).
 */
const meta = {
  title: "Library/Avatar",
  component: Avatar,
  parameters: {
    layout: "centered",
  },
} satisfies Meta<typeof Avatar>

export default meta

type Story = StoryObj<typeof meta>

export const Small: Story = {
  render: () => (
    <Avatar size="sm">
      <AvatarFallback>PT</AvatarFallback>
    </Avatar>
  ),
}

export const Medium: Story = {
  render: () => (
    <Avatar size="md">
      <AvatarFallback className="bg-nav-active text-foreground">AN</AvatarFallback>
    </Avatar>
  ),
}

export const Large: Story = {
  render: () => (
    <Avatar size="lg">
      <AvatarFallback className="bg-primary text-white">JM</AvatarFallback>
    </Avatar>
  ),
}

export const AllSizes: Story = {
  render: () => (
    <div className="flex items-center gap-5">
      <Avatar size="lg">
        <AvatarFallback className="bg-primary text-white">JM</AvatarFallback>
      </Avatar>
      <Avatar size="md">
        <AvatarFallback className="bg-nav-active text-foreground">AN</AvatarFallback>
      </Avatar>
      <Avatar size="sm">
        <AvatarFallback>PT</AvatarFallback>
      </Avatar>
    </div>
  ),
}
