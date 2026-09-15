import * as React from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"

import { SearchBar } from "./SearchBar"

const meta = {
  title: "Library/SearchBar",
  component: SearchBar,
  // `onChange` is required on `SearchBar` itself, but every story below
  // supplies its own via `ControlledSearchBar` wrapping `value`/`onChange`
  // in local state — this default only exists to satisfy the type of
  // `args` before `render` swaps it out; it's never actually invoked.
  args: {
    onChange: () => {},
  },
  argTypes: {
    variant: {
      control: "radio",
      options: ["page", "sunken"],
    },
  },
  // `SearchBar` is `w-full` by design (decision: it fills whatever
  // container a real page gives it — see SearchBar.tsx) — but unlike a
  // `<div>`, a bare `<input>` doesn't grow to fit its own placeholder text
  // in an unconstrained/shrink-wrap context, so without an explicit width
  // here it collapses to the browser's default input size and the mockup's
  // "Search process models" placeholder gets clipped.
  //
  // Deliberately `w-[380px]` (a fixed width), not `max-w-[380px]`: a
  // max-width alone is only an upper bound, and Storybook's "centered"
  // canvas (.storybook/preview.ts) is itself a shrink-to-fit flex
  // container, so nothing anywhere in the chain has a *definite* width for
  // "at most 380px" to apply against — the div would just shrink-wrap the
  // same as before. A fixed width sidesteps that shrink-to-fit ambiguity
  // entirely. (First attempt here used `max-w`; the clipped-placeholder bug
  // was still visible after that "fix" — this is the real one, verified by
  // measuring the rendered element's bounding box, not just eyeballing.)
  decorators: [
    (Story) => (
      <div className="w-[380px]">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SearchBar>

export default meta

type Story = StoryObj<typeof meta>

/**
 * Wraps the controlled `value`/`onChange` props in local state so the story
 * is actually typeable, without adding any state/coupling to the component
 * itself.
 */
function ControlledSearchBar(props: React.ComponentProps<typeof SearchBar>) {
  const [value, setValue] = React.useState(props.value)
  return <SearchBar {...props} value={value} onChange={setValue} />
}

export const Page: Story = {
  render: (args) => <ControlledSearchBar {...args} />,
  args: {
    value: "",
    variant: "page",
    placeholder: "Search process models",
  },
}

export const Sunken: Story = {
  render: (args) => (
    <div className="rounded-xl bg-background p-6">
      <ControlledSearchBar {...args} />
    </div>
  ),
  args: {
    value: "",
    variant: "sunken",
    placeholder: "Search process models",
  },
}

export const WithValue: Story = {
  render: (args) => <ControlledSearchBar {...args} />,
  args: {
    value: "Invoice approval",
    variant: "page",
    placeholder: "Search process models",
  },
}
