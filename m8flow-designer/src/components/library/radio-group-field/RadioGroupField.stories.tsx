import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { RadioGroupField } from "./RadioGroupField"

const meta: Meta<typeof RadioGroupField> = {
  title: "Library/RadioGroupField",
  component: RadioGroupField,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof RadioGroupField>

const scheduleOptions = [
  { label: "Manual", value: "manual" },
  { label: "Scheduled", value: "scheduled" },
]

/** Matches the mockup's "Manual" / "Scheduled" example: an interactive,
 * self-managed radio group so its selected-option state can be clicked in
 * Storybook's canvas. Options come from a plain array — not hardcoded into
 * the component. */
export const Default: Story = {
  render: () => {
    function Wrapper() {
      const [value, setValue] = useState("manual")
      return <RadioGroupField options={scheduleOptions} value={value} onValueChange={setValue} />
    }
    return <Wrapper />
  },
}

export const ThreeOptions: Story = {
  render: () => {
    function Wrapper() {
      const [value, setValue] = useState("weekly")
      return (
        <RadioGroupField
          options={[
            { label: "Daily", value: "daily" },
            { label: "Weekly", value: "weekly" },
            { label: "Monthly", value: "monthly" },
          ]}
          value={value}
          onValueChange={setValue}
        />
      )
    }
    return <Wrapper />
  },
}

export const Disabled: Story = {
  render: () => (
    <RadioGroupField options={scheduleOptions} value="manual" onValueChange={() => {}} disabled />
  ),
}
