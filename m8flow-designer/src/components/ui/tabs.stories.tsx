import type { Meta, StoryObj } from '@storybook/react-vite';

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs';

/**
 * Showcase-only story for `ui/tabs.tsx` (added in ticket 02) — no component
 * code changed here. Reproduces the mockup's "Tabbed pages" example:
 * Diagram (active) | Instances | Files, with a content area below each tab
 * standing in for the real page content (a BPMN-canvas placeholder for the
 * active "Diagram" tab).
 */
const meta = {
  title: 'UI/Tabs',
  component: Tabs,
  tags: ['autodocs'],
} satisfies Meta<typeof Tabs>;

export default meta;

type Story = StoryObj<typeof meta>;

export const TabbedPages: Story = {
  render: () => (
    <Tabs defaultValue="diagram" className="w-full max-w-2xl">
      <TabsList>
        <TabsTrigger value="diagram">Diagram</TabsTrigger>
        <TabsTrigger value="instances">Instances</TabsTrigger>
        <TabsTrigger value="files">Files</TabsTrigger>
      </TabsList>
      <TabsContent value="diagram">
        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
          BPMN canvas placeholder
        </div>
      </TabsContent>
      <TabsContent value="instances">
        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
          Instances list placeholder
        </div>
      </TabsContent>
      <TabsContent value="files">
        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
          Files list placeholder
        </div>
      </TabsContent>
    </Tabs>
  ),
};
