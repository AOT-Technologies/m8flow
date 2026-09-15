import type { Meta, StoryObj } from '@storybook/react-vite';

import { Card } from './card';

/**
 * Showcase-only stories for the existing `ui/card.tsx` primitive — no
 * component code changed here.
 *
 * `ui/card.tsx` ships exactly two variants (see its own doc comment):
 * `default` (shadcn's generated `rounded-xl` + `ring-1 ring-foreground/10`
 * look, HITL-approved for `StatCard.tsx` on the Home mockup) and `bordered`
 * (`rounded-2xl border border-border bg-card shadow-xs`, consolidated from
 * five other consumers). The mockup's plain stat card ("white bg, subtle
 * border, rounded-xl, shadow-xs") doesn't land exactly on either one —
 * `bordered` is the closer match (it's the only variant with a *visible*
 * border and a `shadow-xs`; `default` uses a faint ring and no shadow at
 * all) at the cost of a slightly larger corner radius (`rounded-2xl` vs the
 * mockup's `rounded-xl`), which reads as a minor, acceptable difference.
 * `bordered` is used for all three stories below rather than adding a third
 * variant to the component for a showcase-only need.
 */
const meta = {
  title: 'UI/Card',
  component: Card,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Card>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Default stat card — label + large mono value. */
export const Default: Story = {
  render: () => (
    <Card variant="bordered" className="w-64 p-4">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        Runs 30d
      </div>
      <div className="font-mono text-2xl font-bold text-foreground">128</div>
    </Card>
  ),
};

/**
 * Accent-top card — the mockup's `--nav-active`-colored 3px top border.
 * No existing `Card` prop produces this; it's a one-off `className`
 * (`border-t-[3px] border-t-nav-active`) layered on the `bordered` variant,
 * same pattern already used elsewhere in this app for one-off card accents.
 */
export const AccentTop: Story = {
  render: () => (
    <Card variant="bordered" className="w-64 border-t-[3px] border-t-nav-active p-4">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        Success rate
      </div>
      <div className="font-mono text-2xl font-bold text-success">97%</div>
      <div className="text-[12.5px] text-muted-foreground">Accent-top card</div>
    </Card>
  ),
};

/**
 * Interactive hover-lift card — for clickable list items. `cursor-pointer`
 * plus a transform/shadow transition is a one-off `className`, same as
 * `AccentTop`; there's no dedicated `interactive` variant on `Card`.
 */
export const Interactive: Story = {
  render: () => (
    <Card
      variant="bordered"
      className="w-64 cursor-pointer p-4 transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="text-[15px] font-semibold text-foreground">Interactive card</div>
      <div className="text-[12.5px] text-muted-foreground">
        Lifts on hover. Use for clickable list items.
      </div>
    </Card>
  ),
};

/** All three card styles together, for an at-a-glance diff against the mockup's "Cards" section. */
export const Gallery: Story = {
  render: () => (
    <div className="flex flex-wrap gap-4">
      <Card variant="bordered" className="w-64 p-4">
        <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Runs 30d
        </div>
        <div className="font-mono text-2xl font-bold text-foreground">128</div>
      </Card>
      <Card variant="bordered" className="w-64 border-t-[3px] border-t-nav-active p-4">
        <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Success rate
        </div>
        <div className="font-mono text-2xl font-bold text-success">97%</div>
        <div className="text-[12.5px] text-muted-foreground">Accent-top card</div>
      </Card>
      <Card
        variant="bordered"
        className="w-64 cursor-pointer p-4 transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-md"
      >
        <div className="text-[15px] font-semibold text-foreground">Interactive card</div>
        <div className="text-[12.5px] text-muted-foreground">
          Lifts on hover. Use for clickable list items.
        </div>
      </Card>
    </div>
  ),
};
