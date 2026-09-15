import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { CheckboxField } from "./CheckboxField"

const meta: Meta<typeof CheckboxField> = {
  title: "Library/CheckboxField",
  component: CheckboxField,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof CheckboxField>

/** Matches the mockup's "Notify on completion" example: an interactive,
 * self-managed checkbox so its checked/unchecked states can be clicked in
 * Storybook's canvas. */
export const Default: Story = {
  render: () => {
    function Wrapper() {
      const [checked, setChecked] = useState(false)
      return (
        <CheckboxField label="Notify on completion" checked={checked} onCheckedChange={setChecked} />
      )
    }
    return <Wrapper />
  },
}

export const Checked: Story = {
  render: () => {
    function Wrapper() {
      const [checked, setChecked] = useState(true)
      return (
        <CheckboxField label="Notify on completion" checked={checked} onCheckedChange={setChecked} />
      )
    }
    return <Wrapper />
  },
}

export const Disabled: Story = {
  render: () => (
    <CheckboxField label="Notify on completion" checked={false} onCheckedChange={() => {}} disabled />
  ),
}
