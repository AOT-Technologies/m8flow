import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { Button } from "@/components/ui/button"
import { WizardModal, type WizardModalStep } from "./WizardModal"

const meta: Meta<typeof WizardModal> = {
  title: "Library/WizardModal",
  component: WizardModal,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof WizardModal>

/** The mockup's three-step "setup wizard" example. */
const steps: WizardModalStep[] = [
  {
    title: "Connect a source",
    body: "Choose where this process pulls its trigger data from — a form, an API, or a scheduled timer.",
  },
  {
    title: "Map the fields",
    body: "Match incoming fields to the variables this process model expects.",
  },
  {
    title: "Review & launch",
    body: "Confirm the connection and mapping, then turn the process on.",
  },
]

export const Default: Story = {
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(false)

      return (
        <>
          <Button variant="pill" onClick={() => setOpen(true)}>
            Open setup wizard
          </Button>
          <WizardModal
            open={open}
            steps={steps}
            onClose={() => setOpen(false)}
            onComplete={() => setOpen(false)}
          />
        </>
      )
    }
    return <Wrapper />
  },
}

/**
 * `canContinue` gates the Continue button until the step's own selection is
 * made — the tenant-management "Add Member" wizard's shape (pick a user
 * before "Next" enables, then a busy `continueLabel` while the final step's
 * submit is in flight). Also demonstrates `size="md"` — the same size that
 * real "Add Member" wizard uses, since a step with a picker list like this
 * one is cramped at the default `"sm"` (460px).
 */
export const RequiresSelectionToContinue: Story = {
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(false)
      const [picked, setPicked] = useState<string | null>(null)
      const [submitting, setSubmitting] = useState(false)

      const gatedSteps: WizardModalStep[] = [
        {
          title: "Pick a source",
          canContinue: picked !== null,
          body: (
            <div className="flex flex-col gap-2">
              {["Form", "API", "Scheduled timer"].map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={picked === option ? "pill" : "pill-outline"}
                  onClick={() => setPicked(option)}
                >
                  {option}
                </Button>
              ))}
            </div>
          ),
        },
        {
          title: "Review & launch",
          canContinue: !submitting,
          continueLabel: submitting ? "Launching…" : "Finish",
          body: `Connect from ${picked ?? "—"}, then turn the process on.`,
        },
      ]

      return (
        <>
          <Button variant="pill" onClick={() => setOpen(true)}>
            Open setup wizard
          </Button>
          <WizardModal
            open={open}
            steps={gatedSteps}
            onClose={() => setOpen(false)}
            onComplete={() => {
              setSubmitting(true)
              setTimeout(() => {
                setSubmitting(false)
                setOpen(false)
              }, 600)
            }}
            size="md"
          />
        </>
      )
    }
    return <Wrapper />
  },
}
