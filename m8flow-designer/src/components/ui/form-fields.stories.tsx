import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { AlertCircle } from 'lucide-react';

import { Input } from './input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select';
import { Textarea } from './textarea';

/**
 * Combined showcase for `ui/input.tsx`, `ui/select.tsx`, and
 * `ui/textarea.tsx` — no component code changed for any of them. Reproduces
 * the mockup's "Form fields" grid (text input / select / textarea) plus its
 * "Inline error message" section.
 *
 * The inline-error look (red border + error icon + message below the
 * field) needs **no new prop on `ui/input.tsx`**: it already ships
 * `aria-invalid:border-destructive aria-invalid:ring-3
 * aria-invalid:ring-destructive/20` baked into its className, so passing
 * `aria-invalid` (a real HTML/ARIA attribute, not a custom prop) is
 * sufficient — confirmed by reading `input.tsx` directly rather than
 * assumed. `textarea.tsx` carries the identical `aria-invalid:` styling for
 * the same reason. The top-of-form error banner and below-field error text
 * reuse this app's existing destructive-message convention (`border-
 * destructive/40 bg-destructive/10 text-destructive`, as already used in
 * `AcceptInvitationPage.tsx`, and the `AlertCircle` icon pairing already
 * used in `EditorDialog.tsx`/`FormSchemaEditor.tsx`) rather than inventing
 * a new pattern.
 */
const meta = {
  title: 'UI/Form Fields',
  tags: ['autodocs'],
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

/** The mockup's grid of text input / select / textarea, side by side. */
export const Grid: Story = {
  render: function GridStory() {
    const [status, setStatus] = useState('draft');
    return (
      <div className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Text input" htmlFor="form-fields-name">
          <Input id="form-fields-name" placeholder="e.g. Invoice Approvals" />
        </Field>
        <Field label="Select" htmlFor="form-fields-status">
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger id="form-fields-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="published">Published</SelectItem>
              <SelectItem value="paused">Paused</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Textarea" htmlFor="form-fields-description">
          <Textarea
            id="form-fields-description"
            placeholder="Describe what this process does"
            rows={3}
          />
        </Field>
      </div>
    );
  },
};

/**
 * Inline error message — a top-of-form error banner plus a single invalid
 * field. `aria-invalid` is the only thing driving the red border/ring on
 * the `Input`; everything else (banner, below-field message, icon) is
 * plain markup reusing existing destructive-text conventions.
 */
export const InlineError: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-4">
      <div className="flex items-start gap-2 rounded-[10px] border border-destructive/25 bg-destructive/10 px-4 py-3">
        <AlertCircle className="mt-0.5 size-4 flex-none text-destructive" strokeWidth={2} />
        <span className="text-sm text-destructive">
          Could not save this process model. Check your connection and try again.
        </span>
      </div>
      <Field label="Model name" htmlFor="form-fields-invalid-name">
        <Input id="form-fields-invalid-name" defaultValue="Invoice Approvals" aria-invalid />
      </Field>
      <div className="flex items-center gap-1.5 text-sm text-destructive">
        <AlertCircle className="size-3.5 flex-none" strokeWidth={2} />
        <span>This name is already in use.</span>
      </div>
    </div>
  ),
};
