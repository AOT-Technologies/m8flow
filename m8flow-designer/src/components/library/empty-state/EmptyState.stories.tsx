import type { Meta, StoryObj } from "@storybook/react-vite"
import { Inbox } from "lucide-react"

import { Button } from "@/components/ui/button"

import { EmptyState } from "./EmptyState"

const meta: Meta<typeof EmptyState> = {
  title: "Library/EmptyState",
  component: EmptyState,
  args: {
    title: "No models in this group",
    description: "Create a model here, or clear the filter to see all models.",
  },
}

export default meta

type Story = StoryObj<typeof EmptyState>

// The mockup's exact example: heading + description + a primary/outline
// pill button pair, no icon.
export const Default: Story = {
  args: {
    actions: (
      <>
        <Button variant="pill" size="pill">
          New process model
        </Button>
        <Button variant="pill-outline" size="pill">
          Clear filter
        </Button>
      </>
    ),
  },
}

export const TitleOnly: Story = {
  name: "Title only (no description, no actions)",
  args: {
    description: undefined,
  },
}

export const WithIcon: Story = {
  args: {
    icon: <Inbox className="size-8" aria-hidden="true" />,
    actions: (
      <Button variant="pill" size="pill">
        New process model
      </Button>
    ),
  },
}

export const SingleAction: Story = {
  args: {
    actions: (
      <Button variant="pill" size="pill">
        New process model
      </Button>
    ),
  },
}
