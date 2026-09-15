import { useEffect, useState, type FormEvent } from 'react';

import { ApiError } from '@/lib/api';
import { slugifyProcessModelId } from '@/lib/processModelId';
import { createTemplateWithFiles, type TemplateVisibility } from '@/lib/templatesApi';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type SaveAsTemplateFile = {
  name: string;
  content: Blob;
};

export type SaveAsTemplateDialogProps = {
  open: boolean;
  onClose: () => void;
  defaultName: string;
  getFiles: () => Promise<SaveAsTemplateFile[]>;
  onCreated: (templateId: number) => void;
};

const VISIBILITY_OPTIONS: TemplateVisibility[] = ['PRIVATE', 'TENANT', 'PUBLIC'];
const NAME_MAX = 100;
const NAME_CHARS = /^[A-Za-z0-9 _-]+$/;

export function isSupportedTemplateSourceFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ['.bpmn', '.json', '.dmn', '.md'].some((ext) => lower.endsWith(ext));
}

export function mimeForTemplateSourceFile(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith('.json')) return 'application/json';
  if (lower.endsWith('.md')) return 'text/markdown';
  return 'application/xml';
}

/** Keep the process model's primary file first so the host treats that BPMN as the template's first BPMN. */
export function sortFilesPrimaryFirst<T extends { name: string }>(files: T[], primaryName: string): T[] {
  if (!primaryName) return files;
  const index = files.findIndex((file) => file.name === primaryName);
  if (index <= 0) return files;
  const next = [...files];
  const [primary] = next.splice(index, 1);
  return [primary, ...next];
}

function validateName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return 'Name is required.';
  if (trimmed.length > NAME_MAX) return `Name must be ${NAME_MAX} characters or fewer.`;
  if (!NAME_CHARS.test(trimmed)) {
    return 'Name may only contain letters, numbers, spaces, hyphens and underscores.';
  }
  if (!slugifyProcessModelId(trimmed)) {
    return 'Name must include a letter or number.';
  }
  return null;
}

/**
 * Save as template — packs a process model's .bpmn / .json / .dmn / .md files
 * into a new draft via POST /v1.0/m8flow/templates (multipart). Same field
 * set as the old product modal; layout matches Import template.
 */
export function SaveAsTemplateDialog({
  open,
  onClose,
  defaultName,
  getFiles,
  onCreated,
}: SaveAsTemplateDialogProps) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [visibility, setVisibility] = useState<TemplateVisibility>('PRIVATE');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setDescription('');
    setCategory('');
    setTags('');
    setVisibility('PRIVATE');
    setError(null);
  }, [open, defaultName]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const nameError = validateName(name);
    if (nameError) {
      setError(nameError);
      return;
    }
    const trimmedName = name.trim();
    const templateKey = slugifyProcessModelId(trimmedName);
    setSubmitting(true);
    setError(null);
    try {
      const files = await getFiles();
      if (!files.some((file) => file.name.toLowerCase().endsWith('.bpmn'))) {
        setError('At least one BPMN file is required.');
        return;
      }
      const created = await createTemplateWithFiles(
        {
          templateKey,
          name: trimmedName,
          description: description.trim() || undefined,
          category: category.trim() || undefined,
          tags: tags
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean),
          visibility,
        },
        files,
      );
      onCreated(created.id);
    } catch (err) {
      const fromServer = err instanceof ApiError ? err.serverMessage : undefined;
      setError(fromServer || (err instanceof Error ? err.message : 'Failed to save as template'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Save as template"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="save-as-template-form" disabled={submitting || !name.trim()}>
            {submitting ? 'Creating…' : 'Create template'}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        Creates a draft template from this process model&apos;s BPMN, DMN, form-schema, and markdown files.
      </p>
      <form id="save-as-template-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="save-as-template-name" className="text-xs font-medium text-muted-foreground">
            Name
          </label>
          <Input
            id="save-as-template-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX}
            required
            disabled={submitting}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="save-as-template-description" className="text-xs font-medium text-muted-foreground">
            Description (optional)
          </label>
          <textarea
            id="save-as-template-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            disabled={submitting}
            className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="save-as-template-category" className="text-xs font-medium text-muted-foreground">
              Category (optional)
            </label>
            <Input
              id="save-as-template-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="save-as-template-visibility" className="text-xs font-medium text-muted-foreground">
              Visibility
            </label>
            <select
              id="save-as-template-visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as TemplateVisibility)}
              disabled={submitting}
              className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {VISIBILITY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="save-as-template-tags" className="text-xs font-medium text-muted-foreground">
            Tags (comma-separated, optional)
          </label>
          <Input
            id="save-as-template-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="finance, approval"
            disabled={submitting}
          />
        </div>

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
