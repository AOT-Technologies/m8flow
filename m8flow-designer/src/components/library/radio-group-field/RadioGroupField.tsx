import * as React from "react"

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { cn } from "@/lib/utils"

export interface RadioGroupFieldOption {
  label: React.ReactNode
  value: string
}

export interface RadioGroupFieldProps
  extends Omit<React.ComponentProps<typeof RadioGroup>, "value" | "onValueChange" | "children"> {
  /** Rendered as one labeled row per option, in order. Not hardcoded. */
  options: RadioGroupFieldOption[]
  value: string
  onValueChange: (value: string) => void
  /** Extra classes for each option's clickable row, not the radio itself. */
  optionClassName?: string
}

/**
 * Thin wrapper around `ui/radio-group.tsx` that pairs each `RadioGroupItem`
 * with a label, matching the mockup's "whole row is one click target"
 * pattern (e.g. "Manual" / "Scheduled").
 *
 * A real `<label>` wraps each control and its text — Radix's
 * `RadioGroupItem` renders as a `<button>`, a labelable form control, so the
 * browser natively forwards a click anywhere in the label (including the
 * text) to that radio, no manual click handler needed.
 */
const RadioGroupField = React.forwardRef<
  React.ElementRef<typeof RadioGroup>,
  RadioGroupFieldProps
>(({ options, value, onValueChange, optionClassName, disabled, ...props }, ref) => (
  <RadioGroup ref={ref} value={value} onValueChange={onValueChange} disabled={disabled} {...props}>
    {options.map((option) => (
      <label
        key={option.value}
        data-slot="radio-group-field-option"
        className={cn(
          "inline-flex cursor-pointer items-center gap-2",
          disabled && "cursor-not-allowed opacity-50",
          optionClassName
        )}
      >
        <RadioGroupItem value={option.value} />
        <span className="text-[13.5px] text-foreground">{option.label}</span>
      </label>
    ))}
  </RadioGroup>
))
RadioGroupField.displayName = "RadioGroupField"

export { RadioGroupField }
