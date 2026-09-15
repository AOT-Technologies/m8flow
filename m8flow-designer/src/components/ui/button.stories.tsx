import type { Meta, StoryObj } from '@storybook/react-vite';
import { MoreVertical, Plus } from 'lucide-react';

import { Button } from './button';

/**
 * Showcase-only stories for the existing `ui/button.tsx` primitive — no
 * component code changed here. Reproduces every button shown in the
 * mockup's "Buttons" section using the `pill`/`pill-dark`/`pill-outline`
 * variant family that already exists for exactly this look (see the
 * variant comment in button.tsx), plus the default rounded-lg scale's
 * `ghost`/`link` variants for the "Ghost" example and `size="icon"` for
 * the round icon-only button.
 */
const meta = {
  title: 'UI/Button',
  component: Button,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Sky-blue pill — the mockup's primary call-to-action button. */
export const Primary: Story = {
  args: {
    variant: 'pill',
    children: 'Primary',
  },
};

/** Dark/gunmetal pill — the mockup's secondary-emphasis dark button. */
export const Dark: Story = {
  args: {
    variant: 'pill-dark',
    children: 'Dark',
  },
};

/** Outline pill — the mockup's secondary button. */
export const Secondary: Story = {
  args: {
    variant: 'pill-outline',
    children: 'Secondary',
  },
};

/**
 * The mockup describes "Ghost" as "no border/bg, link-colored text" — that
 * text-color detail is the deciding signal between the two rounded-lg
 * candidates that exist on this component:
 *
 * - `ghost` never sets a text color of its own (inherits plain
 *   `foreground`) and only reveals a `bg-muted` fill on hover — closer to
 *   a toolbar/icon-button treatment than "link-colored text".
 * - `link` renders `text-primary` (this app's link-blue) at rest, with no
 *   background ever, and an underline on hover — matching "link-colored
 *   text" literally, at rest, not just on interaction.
 *
 * `link` was picked for that reason. `ghost` is still exercised in
 * `GhostVariantAlternative` below so both are visible side by side for
 * anyone re-checking this call against the live mockup.
 */
export const Ghost: Story = {
  args: {
    variant: 'link',
    children: 'Ghost',
  },
};

/** The `ghost` variant considered and set aside for `Ghost` above — kept as a visible alternative, not the mockup match. */
export const GhostVariantAlternative: Story = {
  args: {
    variant: 'ghost',
    children: 'Ghost (ghost variant)',
  },
};

export const Disabled: Story = {
  args: {
    variant: 'pill',
    disabled: true,
    children: 'Disabled',
  },
};

export const WithIcon: Story = {
  args: {
    variant: 'pill',
    children: (
      <>
        <Plus className="size-3.5" strokeWidth={2.5} />
        With icon
      </>
    ),
  },
};

/** Icon-only round button — `size="icon"` combined with a pill-shaped variant's rounding, matching the mockup's kebab/dots trigger button. */
export const IconOnly: Story = {
  args: {
    variant: 'pill-outline',
    size: 'icon',
    className: 'rounded-full',
    'aria-label': 'More actions',
    children: <MoreVertical className="size-4" strokeWidth={2.4} />,
  },
};

/** All mockup buttons rendered together, for a single at-a-glance visual diff against the mockup's "Buttons" row. */
export const Gallery: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="pill">Primary</Button>
      <Button variant="pill-dark">Dark</Button>
      <Button variant="pill-outline">Secondary</Button>
      <Button variant="link">Ghost</Button>
      <Button variant="pill" disabled>
        Disabled
      </Button>
      <Button variant="pill">
        <Plus className="size-3.5" strokeWidth={2.5} />
        With icon
      </Button>
      <Button variant="pill-outline" size="icon" className="rounded-full" aria-label="More actions">
        <MoreVertical className="size-4" strokeWidth={2.4} />
      </Button>
    </div>
  ),
};
