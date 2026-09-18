/**
 * M8F-524: the "View XML" dialog, editable. Previously a read-only <pre>.
 *
 * Monaco rather than a <textarea>: `@monaco-editor/react` is already a
 * dependency used for the same job elsewhere in this modeler (TextFileCanvas
 * for .json/.md, EditorDialog for scripts), and hand-editing a few hundred
 * lines of BPMN without line numbers or bracket matching is not a real
 * feature. `xml` is a basic language — tokenizer only, no language worker —
 * so it costs a syntax file, matching how TextFileCanvas pulls in markdown.
 *
 * Lazily imported by ProcessModelModelerPage and only rendered while open:
 * opening a .bpmn file must not pull Monaco (see DiagramCanvas's comment on
 * why its canvases are lazy).
 */
import { useMemo, useState } from 'react';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/editor/editor.all';
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution';

import { Alert } from '@/components/library/alert/Alert';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';

loader.config({ monaco });

/**
 * Well-formedness only, via the platform's own parser — enough to stop a
 * stray `<` or an unclosed tag from being written over a good file, and it
 * needs no XML grammar of our own (codeLint.ts has none).
 *
 * Deliberately *not* a BPMN/DMN schema check: XML that parses but isn't a
 * valid diagram still saves, and the canvas's own import-error banner
 * reports it. That's recoverable — the file is still editable here — so
 * gating on a schema validator we'd have to build isn't worth it.
 */
export function xmlSyntaxError(value: string): string | null {
  if (!value.trim()) return 'XML is empty.';
  const parsed = new DOMParser().parseFromString(value, 'application/xml');
  const failure = parsed.querySelector('parsererror');
  if (!failure) return null;
  const firstLine = failure.textContent?.trim().split('\n')[0];
  return firstLine ? `Invalid XML: ${firstLine}` : 'Invalid XML.';
}

export type XmlEditorDialogProps = {
  fileName: string;
  /** The saved snapshot the editor starts from; `null` while the export is
   * still in flight. */
  xml: string | null;
  /**
   * The in-progress edit, owned by the page. `null` means "untouched, show
   * `xml`". It lives above this component on purpose: held as local state
   * seeded from `xml`, any remount of this dialog silently restored the
   * saved snapshot over the user's edits (M8F-524 follow-up — the editor
   * came back showing the original XML after "Keep editing"). The page does
   * not remount, so the draft survives whatever happens to the dialog.
   */
  draft: string | null;
  onDraftChange: (next: string) => void;
  /** Failure of the export itself — nothing to edit, so the editor is hidden. */
  loadError: string | null;
  /** Same gate as Delete / New file: no Save button for a viewer. */
  canEdit: boolean;
  onClose: () => void;
  /** Rejects on a failed PUT; the message is shown and the dialog stays open. */
  onSave: (next: string) => Promise<void>;
};

export function XmlEditorDialog({
  fileName,
  xml,
  draft,
  onDraftChange,
  loadError,
  canEdit,
  onClose,
  onSave,
}: XmlEditorDialogProps) {
  // Only transient dialog chrome is local state — losing any of it to a
  // remount costs nothing, unlike the draft.
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Set by any close gesture while there are unsaved edits; opens the
  // save/discard modal stacked over this one.
  const [confirmingClose, setConfirmingClose] = useState(false);

  const value = draft ?? xml ?? '';
  const syntaxError = useMemo(() => xmlSyntaxError(value), [value]);
  const dirty = xml != null && draft != null && draft !== xml;
  const canSave = canEdit && dirty && !saving && !syntaxError;

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(value);
    } catch (err) {
      // Drop the confirm modal so the error is readable, with the edits
      // still in the editor to retry or discard.
      setConfirmingClose(false);
      setSaveError(err instanceof Error ? err.message : 'Failed to save XML');
    } finally {
      setSaving(false);
    }
  }

  /** Every close gesture — Cancel, the X, Esc, an overlay click — routes
   * here, so unsaved edits can't be dropped by any of them. */
  function requestClose() {
    if (saving) return;
    if (dirty && canEdit) {
      setConfirmingClose(true);
      return;
    }
    onClose();
  }

  return (
    <>
      <Modal
        open
        onOpenChange={(next) => { if (!next) requestClose(); }}
        title="View XML"
        size="lg"
        footer={
          <>
            <Button type="button" variant="outline" disabled={saving} onClick={requestClose}>
              {canEdit ? 'Cancel' : 'Close'}
            </Button>
            {canEdit ? (
              <Button type="button" disabled={!canSave} onClick={() => void handleSave()}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            ) : null}
          </>
        }
      >
        <p className="-mt-1 flex-none text-sm text-muted-foreground">{fileName}</p>
        {loadError ? (
          <Alert tone="error">{loadError}</Alert>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border">
              <Editor
                language="xml"
                value={value}
                onChange={(next) => onDraftChange(next ?? '')}
                height="100%"
                options={{
                  ariaLabel: 'XML editor',
                  readOnly: xml == null || !canEdit,
                  glyphMargin: false,
                  folding: true,
                  lineNumbersMinChars: 3,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  fontSize: 13,
                  tabSize: 2,
                }}
              />
            </div>
            {syntaxError || saveError ? (
              <Alert tone="error">{saveError ?? syntaxError}</Alert>
            ) : null}
          </>
        )}
      </Modal>

      {/* Stacked over the editor rather than replacing its footer, so the
          choice reads as the warning it is. Radix hands the focus trap and
          Esc to whichever dialog is on top, so the editor underneath stays
          mounted with the edits intact. */}
      {confirmingClose ? (
        <Modal
          open
          onOpenChange={(next) => { if (!next && !saving) setConfirmingClose(false); }}
          title="Unsaved changes"
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => setConfirmingClose(false)}
              >
                Keep editing
              </Button>
              <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
                Discard
              </Button>
              <Button type="button" disabled={!canSave} onClick={() => void handleSave()}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted-foreground">
            {syntaxError
              ? `Your edits to ${fileName} cannot be saved while the XML is not well-formed. Keep editing to fix it, or discard them.`
              : `Save your edits to ${fileName}, or discard them and close?`}
          </p>
        </Modal>
      ) : null}
    </>
  );
}
