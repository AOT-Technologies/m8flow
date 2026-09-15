import * as React from "react"

import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

export interface ToggleSwitchProps
  extends Omit<React.ComponentProps<typeof Switch>, "checked" | "onCheckedChange"> {
  /** Text shown next to the switch. Clicking it toggles the switch too. */
  label: React.ReactNode
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  /** Extra classes for the outer clickable row, not the switch itself. */
  containerClassName?: string
}

/**
 * Thin wrapper around `ui/switch.tsx` that pairs it with a label, matching
 * the mockup's "whole row is one click target" pattern. A real `<label>`
 * wraps both the switch and the text — `<button>` is a labelable form
 * control, so the browser natively forwards a click anywhere in the label
 * (including the text) to the switch, no manual click handler needed.
 */
const ToggleSwitch = React.forwardRef<React.ElementRef<typeof Switch>, ToggleSwitchProps>(
  ({ label, checked, onCheckedChange, containerClassName, className, disabled, ...props }, ref) => (
    <label
      data-slot="toggle-switch"
      className={cn(
        "inline-flex cursor-pointer items-center gap-[10px]",
        disabled && "cursor-not-allowed opacity-50",
        containerClassName
      )}
    >
      <Switch
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
ToggleSwitch.displayName = "ToggleSwitch"

export { ToggleSwitch }
