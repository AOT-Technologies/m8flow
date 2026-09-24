import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { XmlEditorDialog } from './XmlEditorDialog';

const ORIGINAL = '<bpmn:definitions xmlns:bpmn="http://bpmn" id="original" />';
const EDITED = '<bpmn:definitions xmlns:bpmn="http://bpmn" id="edited" />';

/** Stands in for the page: owns the draft, and can unmount/remount the
 * dialog the way a re-render or a re-suspend does in the browser. */
function Host({ xml = ORIGINAL }: { xml?: string | null }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [mounted, setMounted] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setMounted((on) => !on)}>
        remount
      </button>
      {mounted ? (
        <XmlEditorDialog
          fileName="invoice-approval.bpmn"
          xml={xml}
          draft={draft}
          onDraftChange={setDraft}
          loadError={null}
          canEdit
          onClose={() => {}}
          onSave={async () => {}}
        />
      ) : null}
    </>
  );
}

describe('XmlEditorDialog draft ownership', () => {
  it('keeps the edit when the dialog is remounted', async () => {
    render(<Host />);

    fireEvent.change(await screen.findByRole('textbox', { name: 'XML editor' }), {
      target: { value: EDITED },
    });

    // A remount is what loses the edit when the draft is dialog-local state
    // seeded from the `xml` prop.
    // The host button sits outside the modal, which Radix aria-hides.
    const remount = () =>
      fireEvent.click(screen.getByRole('button', { name: 'remount', hidden: true }));
    remount();
    remount();

    expect(await screen.findByRole('textbox', { name: 'XML editor' })).toHaveValue(EDITED);
  });

  it('keeps the edit when the same xml snapshot is handed down again', async () => {
    const { rerender } = render(<Host />);

    fireEvent.change(await screen.findByRole('textbox', { name: 'XML editor' }), {
      target: { value: EDITED },
    });
    rerender(<Host xml={ORIGINAL} />);

    expect(screen.getByRole('textbox', { name: 'XML editor' })).toHaveValue(EDITED);
  });

  it('shows the snapshot until the user edits it', async () => {
    const onDraftChange = vi.fn();
    const { rerender } = render(
      <XmlEditorDialog
        fileName="a.bpmn"
        xml={null}
        draft={null}
        onDraftChange={onDraftChange}
        loadError={null}
        canEdit
        onClose={() => {}}
        onSave={async () => {}}
      />,
    );
    expect(await screen.findByRole('textbox', { name: 'XML editor' })).toHaveValue('');

    rerender(
      <XmlEditorDialog
        fileName="a.bpmn"
        xml={ORIGINAL}
        draft={null}
        onDraftChange={onDraftChange}
        loadError={null}
        canEdit
        onClose={() => {}}
        onSave={async () => {}}
      />,
    );
    expect(screen.getByRole('textbox', { name: 'XML editor' })).toHaveValue(ORIGINAL);
  });
});
