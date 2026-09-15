import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { Button } from "@/components/ui/button"
import { Modal } from "./Modal"

const meta: Meta<typeof Modal> = {
  title: "Library/Modal",
  component: Modal,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof Modal>

/**
 * Reproduces the mockup's "New group" example: a title, a description
 * paragraph, a single text input, and a Cancel/Create-group footer pair.
 * The form itself lives entirely in the story — `Modal` only supplies the
 * chrome around it.
 */
export const Default: Story = {
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(false)
      const [groupName, setGroupName] = useState("")

      return (
        <>
          <Button variant="pill" onClick={() => setOpen(true)}>
            Open modal
          </Button>
          <Modal
            open={open}
            onOpenChange={setOpen}
            title="New group"
            footer={
              <>
                <Button type="button" variant="pill-outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="button" variant="pill" onClick={() => setOpen(false)}>
                  Create group
                </Button>
              </>
            }
          >
            <p className="mb-4 text-[13.5px] text-muted-foreground">
              Groups organize related process models together.
            </p>
            <label className="block text-sm font-medium text-foreground">
              Group name
              <input
                type="text"
                value={groupName}
                onChange={(event) => setGroupName(event.target.value)}
                className="mt-1.5 block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-3 focus:ring-ring/50"
                placeholder="e.g. Onboarding"
              />
            </label>
          </Modal>
        </>
      )
    }
    return <Wrapper />
  },
}

/**
 * `size="md"` (720px) — the same auto-height behavior as the default `"sm"`
 * (460px) at a wider fixed width, for content wider than a single-column
 * form but still short: a picker list, or a multi-step wizard with a
 * scrollable list (e.g. `WizardModal`'s own `size` passthrough).
 */
export const Medium: Story = {
  name: 'size="md" (wider content)',
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(false)

      return (
        <>
          <Button variant="pill" onClick={() => setOpen(true)}>
            Open medium modal
          </Button>
          <Modal
            open={open}
            onOpenChange={setOpen}
            title="Add Member"
            size="md"
            footer={
              <>
                <Button type="button" variant="pill-outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="button" variant="pill" onClick={() => setOpen(false)}>
                  Next
                </Button>
              </>
            }
          >
            <p className="mb-4 text-[13.5px] text-muted-foreground">
              Pick an existing shared-realm user. This is not an email invitation.
            </p>
            <div className="flex flex-col gap-1 rounded-lg border border-border p-2">
              {["Ed Itor", "Rev Iewer", "Ad Min"].map((name) => (
                <div key={name} className="rounded-md px-2 py-1.5 text-sm text-foreground">
                  {name}
                </div>
              ))}
            </div>
          </Modal>
        </>
      )
    }
    return <Wrapper />
  },
}

/**
 * `size="lg"` — for genuinely large embedded content (e.g. a code editor):
 * 1100px wide, capped at 80vh, `DialogContent` becomes a flex column so a
 * tall child (here, a placeholder editor pane) can fill the remaining space
 * via `min-h-0 flex-1` instead of growing the dialog past the viewport.
 */
export const Large: Story = {
  name: 'size="lg" (large embedded content)',
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(false)

      return (
        <>
          <Button variant="pill" onClick={() => setOpen(true)}>
            Open large modal
          </Button>
          <Modal
            open={open}
            onOpenChange={setOpen}
            title="Edit Script — Approve request"
            size="lg"
            footer={
              <>
                <Button type="button" variant="pill-outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="button" variant="pill" onClick={() => setOpen(false)}>
                  Save
                </Button>
              </>
            }
          >
            <div className="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-muted/40 font-mono text-xs text-muted-foreground">
              (embedded editor fills this flex-1 area)
            </div>
          </Modal>
        </>
      )
    }
    return <Wrapper />
  },
}
