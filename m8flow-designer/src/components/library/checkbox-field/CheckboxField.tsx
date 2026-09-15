import * as React from "react"

import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"

export interface CheckboxFieldProps
  extends Omit<React.ComponentProps<typeof Checkbox>, "checked" | "onCheckedChange"> {
  /** Text shown next to the checkbox. Clicking it toggles the checkbox too. */
  label: React.ReactNode
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  /** Extra classes for the outer clickable row, not the checkbox itself. */
  containerClassName?: string
}

/**
 * Thin wrapper around `ui/checkbox.tsx` that pairs it with a label, matching
 * the mockup's "whole row is one click target" pattern. Named `CheckboxField`
 * (not `Checkbox`) so it doesn't collide with `ui/checkbox.tsx`'s own export
 * when both are imported in the same file/story.
 *
 * A real `<label>` wraps both the checkbox and the text — Radix's
 * `Checkbox.Root` renders as a `<button>`, a labelable form control, so the
 * browser natively forwards a click anywhere in the label (including the
 * text) to the checkbox, no manual click handler needed.
 */
const CheckboxField = React.forwardRef<React.ElementRef<typeof Checkbox>, CheckboxFieldProps>(
  ({ label, checked, onCheckedChange, containerClassName, className, disabled, ...props }, ref) => (
    <label
      data-slot="checkbox-field"
      className={cn(
        "inline-flex cursor-pointer items-center gap-[10px]",
        disabled && "cursor-not-allowed opacity-50",
        containerClassName
      )}
    >
      <Checkbox
        ref={ref}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className={className}
        {...props}
      />
      <span className="text-[13.5px] text-foreground">{label}</span>
    </label>
  )
)
CheckboxField.displayName = "CheckboxField"

export { CheckboxField }
