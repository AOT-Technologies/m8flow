import type { Meta, StoryObj } from "@storybook/react-vite"

import { Alert } from "./Alert"

const meta: Meta<typeof Alert> = {
  title: "Library/Alert",
  component: Alert,
  args: {
    tone: "info",
    children: "A new version of the connector SDK is available.",
  },
  argTypes: {
    tone: {
      control: "select",
      options: ["success", "warning", "error", "info"],
    },
  },
}

export default meta

type Story = StoryObj<typeof Alert>

// The mockup's four example alerts, one per tone.
export const Success: Story = {
  args: {
    tone: "success",
    children: "Process model published successfully.",
  },
}

export const Warning: Story = {
  args: {
    tone: "warning",
    children: "This model has not run in 6 days.",
  },
}

export const Info: Story = {
  args: {
    tone: "info",
    children: "A new version of the connector SDK is available.",
  },
}

export const Error: Story = {
  args: {
    tone: "error",
    children: "Could not save this process model. Check your connection and try again.",
  },
}

export const AllTones: Story = {
  render: () => (
    <div className="flex max-w-[560px] flex-col gap-2.5">
      <Alert tone="success">Process model published successfully.</Alert>
      <Alert tone="warning">This model has not run in 6 days.</Alert>
      <Alert tone="info">A new version of the connector SDK is available.</Alert>
      <Alert tone="error">
        Could not save this process model. Check your connection and try again.
      </Alert>
    </div>
  ),
}
