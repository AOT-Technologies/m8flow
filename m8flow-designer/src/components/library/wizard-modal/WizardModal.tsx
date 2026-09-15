import * as React from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Modal } from "@/components/library/modal/Modal"

export interface WizardModalStep {
  title: React.ReactNode
  body: React.ReactNode
  /**
   * Gates the Continue/Finish button for this step — disabled whenever this
   * is `false`. Defaults to `true` (unchanged for any caller that doesn't
   * pass it). Re-evaluated on every render, so a caller can flip it live as
   * the step's own selection state changes (component-adoption map, ticket
   * 12 follow-up — tenant-management's "Add Member" wizard needs "Next"
   * disabled until a user is picked, and "Add" disabled while the final
   * submit is in flight — this is the gap the map's own "Not yet specified"
   * section flagged when `WizardModal` had only one candidate consumer).
   */
  canContinue?: boolean
  /**
   * Overrides the Continue/Finish button's content for this step — e.g. a
   * busy "Adding…" label (with a leading icon) while the final step's
   * `onComplete` is in flight. Defaults to "Continue" / "Finish" (the last
   * step), unchanged for any caller that doesn't pass it.
   */
  continueLabel?: React.ReactNode
  /**
   * `data-testid` applied to the Continue/Finish button for this step —
   * lets an existing per-step test id survive onto the single shared
   * button `WizardModal` renders. Omit for no testid (unchanged default).
   */
  continueTestId?: string
}

export interface WizardModalProps {
  open: boolean
  /** The wizard's steps, in order. Both the header title and the body swap
   * per-step (the mockup's "Connect a source" / "Map the fields" /
   * "Review & launch" example). */
  steps: WizardModalStep[]
  /** Called when the dialog should close before the wizard finished — the
   * built-in round close (X) button, Escape, or an overlay click. */
  onClose: () => void
  /** Called when "Finish" (Continue on the final step) is activated. The
   * wizard doesn't close itself first — callers decide whether finishing
   * also closes the dialog. */
  onComplete: () => void
  /** Forwarded straight to the underlying `Modal`'s own `size` prop — see
   * its doc comment for the three tiers. Defaults to `"sm"` (460px),
   * unchanged for any caller that doesn't pass it. A step with a scrollable
   * list (a search box + picker rows, e.g. `tenant-management`'s "Add
   * Member") typically wants `"md"` — `"sm"` is cramped once a step's body
   * grows past a couple of plain form fields. */
  size?: "sm" | "md" | "lg"
}

/**
 * Built on top of `Modal`, adding the mockup's "Multi-page modal" chrome:
 * step dots, a "Step N of M" label, per-step title/body content, and
 * Back/Continue-or-Finish footer buttons (Back disabled on step 1, the
 * final step's button reads "Finish").
 *
 * Manages its own current-step state internally — callers only pass `steps`
 * plus `onClose`/`onComplete`, matching the mockup's own state model
 * (`step`, `stepOpen`). The step resets back to the first one every time the
 * wizard transitions from closed to open, so reopening it always starts
 * fresh.
 */
function WizardModal({ open, steps, onClose, onComplete, size }: WizardModalProps) {
  const [step, setStep] = React.useState(0)

  React.useEffect(() => {
    if (open) {
      setStep(0)
    }
  }, [open])

  const stepCount = steps.length
  const activeStep = Math.min(step, Math.max(stepCount - 1, 0))
  const current = steps[activeStep]
  const isFirstStep = activeStep === 0
  const isLastStep = activeStep >= stepCount - 1
  const canContinue = current?.canContinue ?? true

  function handleBack() {
    setStep((prev) => Math.max(0, prev - 1))
  }

  function handleContinue() {
    if (isLastStep) {
      onComplete()
      return
    }
    setStep((prev) => Math.min(stepCount - 1, prev + 1))
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose()
        }
      }}
      title={current?.title}
      size={size}
      footer={
        <div className="flex w-full items-center justify-between gap-2.5">
          <Button type="button" variant="pill-outline" onClick={handleBack} disabled={isFirstStep}>
            Back
          </Button>
          <Button
            type="button"
            variant="pill"
            onClick={handleContinue}
            disabled={!canContinue}
            data-testid={current?.continueTestId}
          >
            {current?.continueLabel ?? (isLastStep ? "Finish" : "Continue")}
          </Button>
        </div>
      }
    >
      <div data-slot="wizard-modal-steps" className="mb-[18px] flex items-center gap-1.5">
        {steps.map((_, index) => (
          <span
            key={index}
            aria-hidden="true"
            className={cn("h-1 w-5 rounded-full", index <= activeStep ? "bg-nav-active" : "bg-muted")}
          />
        ))}
        <span className="ml-1.5 text-xs text-muted-foreground">
          Step {activeStep + 1} of {stepCount}
        </span>
      </div>
      <div className="mb-5 min-h-24 text-[13.5px] leading-normal text-muted-foreground">
        {current?.body}
      </div>
    </Modal>
  )
}

export { WizardModal }
