import type { Meta, StoryObj } from "@storybook/react-vite"
import { Copy, ExternalLink, Files, Link2, Pencil, Trash2 } from "lucide-react"

import { ActionMenu } from "./ActionMenu"

const meta: Meta<typeof ActionMenu> = {
  title: "Library/ActionMenu",
  component: ActionMenu,
  parameters: {
    layout: "centered",
  },
}

export default meta

type Story = StoryObj<typeof ActionMenu>

// Matches `ProcessInstancesList.tsx`'s row kebab: small, unbordered,
// read-only local actions (no lifecycle/destructive actions).
export const Row: Story = {
  args: {
    triggerLabel: "Instance actions",
    items: [
      { label: "Open", icon: <ExternalLink className="size-3.5" />, onSelect: () => {} },
      { label: "Copy instance ID", icon: <Copy className="size-3.5" />, onSelect: () => {} },
      { label: "Copy link", icon: <Link2 className="size-3.5" />, onSelect: () => {} },
    ],
  },
}

// Matches `ProcessesModelsList.tsx`'s row kebab: same small shape, with a
// destructive "Delete" action.
export const RowWithDestructiveAction: Story = {
  args: {
    triggerLabel: "More actions",
    items: [
      { label: "Open", icon: <ExternalLink className="size-3.5" />, onSelect: () => {} },
      { label: "Delete", icon: <Trash2 className="size-3.5" />, destructive: true, onSelect: () => {} },
    ],
  },
}

// Matches `HeaderActionsMenu.tsx`: larger, bordered, card-background
// trigger, with a visible-but-inert action (disabled, not omitted) for a
// permission the current user lacks.
export const Header: Story = {
  args: {
    triggerLabel: "More actions",
    size: "header",
    contentClassName: "w-52",
    items: [
      { label: "Edit identity", icon: <Pencil className="size-3.5" />, onSelect: () => {} },
      { label: "Copy", icon: <Copy className="size-3.5" />, onSelect: () => {} },
      {
        label: "Save as template",
        icon: <Files className="size-3.5" />,
        disabled: true,
        onSelect: () => {},
      },
    ],
  },
}
