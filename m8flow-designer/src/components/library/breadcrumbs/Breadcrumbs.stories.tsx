import type { Meta, StoryObj } from "@storybook/react-vite"

import { BackLink, Breadcrumbs } from "./Breadcrumbs"

const meta = {
  title: "Library/Breadcrumbs",
  component: Breadcrumbs,
} satisfies Meta<typeof Breadcrumbs>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    items: [
      { label: "Processes", href: "#" },
      { label: "Invoice Approvals / Finance", href: "#" },
      { label: "Two-step invoice approval" },
    ],
  },
}

export const LongFinalCrumbTruncationSafe: Story = {
  name: "Long final crumb (truncation-safe)",
  args: {
    items: [
      { label: "Processes", href: "#" },
      { label: "Invoice Approvals / Finance", href: "#" },
      {
        label:
          "Two-step-invoice-approval-with-an-unusually-long-process-model-name-that-should-wrap-instead-of-overflowing-its-container",
      },
    ],
  },
  decorators: [
    (Story) => (
      <div className="max-w-xs rounded-md border border-border p-3">
        <Story />
      </div>
    ),
  ],
}

export const BackLinkVariant: StoryObj<typeof BackLink> = {
  name: "Back link variant",
  render: (args) => <BackLink {...args} />,
  args: {
    href: "#",
    children: "Back link variant",
  },
}

// Same router-adapter stand-in as Breadcrumbs' own CustomLinkComponent story
// (component-adoption map, ticket 07) — proves BackLink can opt into
// client-side navigation the same way, without a router dependency baked
// into the component itself.
export const BackLinkCustomLinkComponent: StoryObj<typeof BackLink> = {
  name: "Back link (router adapter stand-in)",
  render: (args) => <BackLink {...args} />,
  args: {
    href: "#",
    children: "All processes",
    LinkComponent: ({ href, className, children }) => (
      <a href={href} className={className} data-fake-router-link="true">
        {children}
      </a>
    ),
  },
}

// Stand-in for a `react-router-dom` `Link` adapter (Storybook has no router
// context to render a real one against) — proves a caller can swap in
// client-side navigation without `Breadcrumbs` itself depending on a router
// (component-adoption map, ticket 22).
export const CustomLinkComponent: Story = {
  name: "Custom LinkComponent (router adapter stand-in)",
  args: {
    items: [
      { label: "Processes", href: "#" },
      { label: "Invoice Approvals / Finance", href: "#" },
      { label: "Two-step invoice approval" },
    ],
    LinkComponent: ({ href, className, children }) => (
      <a href={href} className={className} data-fake-router-link="true">
        {children}
      </a>
    ),
  },
}

// Every real page that's adopted `Breadcrumbs` so far wants `text-info`
// (blue) instead of the mockup's own `text-primary` (pink) — override via
// `linkClassName` rather than baking `text-info` in as the new default
// (component-adoption map, ticket 24).
export const CustomLinkColor: Story = {
  name: "Custom link color (linkClassName)",
  args: {
    items: [
      { label: "Processes", href: "#" },
      { label: "Invoice Approvals / Finance", href: "#" },
      { label: "Two-step invoice approval" },
    ],
    linkClassName: "text-info",
  },
}

// Every confirmed consumer whose last crumb is a technical identifier
// (an instance id here) rather than prose wants `font-mono` instead of the
// default plain prose styling — override via `lastClassName` rather than
// baking `font-mono` in as the new default (component-adoption map, ticket
// 26).
export const CustomLastCrumbStyle: Story = {
  name: "Custom last-crumb style (lastClassName)",
  args: {
    items: [
      { label: "Process Instances", href: "#" },
      { label: "Invoice Approval #1042" },
    ],
    linkClassName: "text-info",
    lastClassName: "font-mono",
  },
}
