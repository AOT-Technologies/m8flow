import { useEffect, useState, type FormEvent } from 'react';

import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const TYPED = [
  { value: 'bpmn', label: 'BPMN', suffix: '.bpmn' },
  { value: 'dmn', label: 'DMN', suffix: '.dmn' },
  { value: 'json', label: 'JSON', suffix: '.json' },
  { value: 'md', label: 'Markdown', suffix: '.md' },
] as const;

type FileKind = (typeof TYPED)[number]['value'] | 'upload';

export function fileOpensInModeler(name: string): boolean {
  const lower = name.toLowerCase();
  return (
    lower.endsWith('.bpmn') ||
    lower.endsWith('.dmn') ||
    lower.endsWith('.json') ||
    lower.endsWith('.md')
  );
}

function withSuffix(name: string, suffix: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  return trimmed.toLowerCase().endsWith(suffix) ? trimmed : `${trimmed}${suffix}`;
}

export type AddProcessModelFileDialogProps = {
  open: boolean;
  onClose: () => void;
  existingNames: string[];
  onCreate: (input: { file_name: string; content?: string }) => Promise<void>;
  onCreated: (fileName: string) => void;
};

export function AddProcessModelFileDialog({
  open,
  onClose,
  existingNames,
  onCreate,
  onCreated,
}: AddProcessModelFileDialogProps) {
  const [kind, setKind] = useState<FileKind>('bpmn');
  const [fileName, setFileName] = useState('');
  const [uploadText, setUploadText] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setKind('bpmn');
    setFileName('');
    setUploadText(null);
    setError(null);
  }, [open]);

  const typed = TYPED.find((row) => row.value === kind);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const resolved = typed ? withSuffix(fileName, typed.suffix) : fileName.trim();
    if (!resolved) return;
    if (existingNames.includes(resolved)) {
      setError('A file with this name already exists.');
      return;
    }
    if (kind === 'upload' && uploadText == null) {
      setError('Choose a file to upload.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const input =
        kind === 'upload'
          ? { file_name: resolved, content: uploadText ?? '' }
          : { file_name: resolved };
      await onCreate(input);
      onCreated(resolved);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add file');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Add file"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="add-pm-file-form" disabled={submitting || !fileName.trim()}>
            {submitting ? 'Adding…' : 'Add file'}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        BPMN, DMN, JSON, and Markdown open in the modeler.
      </p>
      <form id="add-pm-file-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          Type
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as FileKind);
              setUploadText(null);
              setError(null);
            }}
            aria-label="File type"
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {TYPED.map((row) => (
              <option key={row.value} value={row.value}>
                {row.label}
              </option>
            ))}
            <option value="upload">Upload</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          File name
          <Input
            value={fileName}
            onChange={(e) => setFileName(e.target.value)}
            placeholder={typed ? `diagram${typed.suffix}` : 'notes.txt'}
            aria-label="File name"
            required
          />
        </label>

        {kind === 'upload' ? (
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            File
            <input
              type="file"
              aria-label="Upload file"
              accept=".bpmn,.dmn,.json,.md,.txt,.xml,.svg,.html,.css"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) {
                  setUploadText(null);
                  return;
                }
                if (!fileName.trim()) setFileName(file.name);
                const reader = new FileReader();
                reader.onload = () => {
                  setUploadText(typeof reader.result === 'string' ? reader.result : '');
                };
                reader.readAsText(file);
              }}
            />
          </label>
        ) : null}

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
