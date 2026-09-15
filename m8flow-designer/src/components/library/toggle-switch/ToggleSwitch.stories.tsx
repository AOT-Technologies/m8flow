import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { ToggleSwitch } from "./ToggleSwitch"

const meta: Meta<typeof ToggleSwitch> = {
  title: "Library/ToggleSwitch",
  component: ToggleSwitch,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof ToggleSwitch>

/** Matches the mockup's "Auto-retry on failure" example: an interactive,
 * self-managed toggle so its checked/unchecked states can be clicked in
 * Storybook's canvas. */
export const Default: Story = {
  render: () => {
    function Wrapper() {
      const [checked, setChecked] = useState(false)
      return (
        <ToggleSwitch label="Auto-retry on failure" checked={checked} onCheckedChange={setChecked} />
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
        <ToggleSwitch label="Auto-retry on failure" checked={checked} onCheckedChange={setChecked} />
      )
    }
    return <Wrapper />
  },
}

export const Disabled: Story = {
  render: () => <ToggleSwitch label="Auto-retry on failure" checked={false} onCheckedChange={() => {}} disabled />,
}
