import type { Meta, StoryObj } from '@storybook/react-vite';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip';

/**
 * Showcase-only story for `ui/tooltip.tsx` (added in ticket 02) — no
 * component code changed here. Reproduces the mockup's tooltip example: a
 * round "?" info trigger that reveals a dark pill ("Runs every 15 minutes")
 * above it on hover.
 *
 * `Tooltip` renders nothing on its own without a `TooltipProvider`
 * ancestor (confirmed by reading `tooltip.tsx` — `TooltipProvider` is
 * `TooltipPrimitive.Provider`, required by Radix for hover-delay
 * coordination), so every story here wraps its example in one.
 */
const meta = {
  title: 'UI/Tooltip',
  component: Tooltip,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Tooltip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const InfoTooltip: Story = {
  render: () => (
    <TooltipProvider>
      <Tooltip defaultOpen>
        <TooltipTrigger asChild>
          <span className="flex size-[22px] cursor-default items-center justify-center rounded-full border-[1.5px] border-border text-xs font-semibold text-muted-foreground">
            ?
          </span>
        </TooltipTrigger>
        <TooltipContent>Runs every 15 minutes</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ),
};
