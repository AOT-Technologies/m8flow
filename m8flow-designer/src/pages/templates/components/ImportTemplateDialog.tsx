import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { importTemplateZip, TEMPLATE_VISIBILITY_OPTIONS, type TemplateVisibility } from '@/lib/templatesApi';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type ImportTemplateDialogProps = {
  open: boolean;
  onClose: () => void;
  /** Fires with the newly-created template's numeric id on success. */
  onImported: (templateId: number) => void;
};

/**
 * "Import" (Template modeler map, ticket 04) — `POST
 * /v1.0/m8flow/templates/import`, a zip previously produced by Export.
 * No auto-slug from a file name: `template_key`/`name` are typed
 * explicitly, same as `createTemplate`'s own required fields — the
 * backend has no "infer metadata from the zip" path to defer to.
 */
export function ImportTemplateDialog({ open, onClose, onImported }: ImportTemplateDialogProps) {
  const { t } = useTranslation();
  // `file` is tracked as real state, not read from `fileRef.current.files`
  // at submit time — found live (a real bug, not just a test artifact):
  // typing into any *other* field re-renders this form, and React's own
  // input-value bookkeeping for `<input type="file">` can clear a
  // manually-assigned `.files` list across that re-render (file inputs
  // link `.value`/`.files` together; React's reconciliation of an
  // uncontrolled input can touch `.value`). `fileRef` is kept only to
  // reset the native input's own displayed filename when the dialog
  // reopens — it's never read for the actual File object anymore.
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [templateKey, setTemplateKey] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [visibility, setVisibility] = useState<TemplateVisibility>('PRIVATE');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setTemplateKey('');
    setName('');
    setDescription('');
    setCategory('');
    setTags('');
    setVisibility('PRIVATE');
    setError(null);
    if (fileRef.current) fileRef.current.value = '';
  }, [open]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !templateKey.trim() || !name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await importTemplateZip(file, {
        templateKey: templateKey.trim(),
        name: name.trim(),
        description: description.trim() || undefined,
        category: category.trim() || undefined,
        tags: tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
        visibility,
      });
      onImported(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('templates.errors.importTemplate'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('templates.importDialog.title')}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            form="import-template-form"
            disabled={submitting || !file || !templateKey.trim() || !name.trim()}
          >
            {submitting ? t('templates.importDialog.importing') : t('templates.import')}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">{t('templates.importDialog.intro')}</p>
      <form id="import-template-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="import-file" className="text-xs font-medium text-muted-foreground">
            {t('templates.importDialog.zipFile')}
          </label>
          <input
            id="import-file"
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="import-key" className="text-xs font-medium text-muted-foreground">
            {t('templates.importDialog.templateKey')}
          </label>
          <Input
            id="import-key"
            value={templateKey}
            onChange={(e) => setTemplateKey(e.target.value)}
            placeholder="invoice-approval-v2"
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="import-name" className="text-xs font-medium text-muted-foreground">
            {t('common.name')}
          </label>
          <Input id="import-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="import-description" className="text-xs font-medium text-muted-foreground">
            {t('common.descriptionOptional')}
          </label>
          <textarea
            id="import-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="import-category" className="text-xs font-medium text-muted-foreground">
              {t('templates.importDialog.categoryOptional')}
            </label>
            <Input id="import-category" value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="import-visibility" className="text-xs font-medium text-muted-foreground">
              {t('templates.visibility.label')}
            </label>
            <Select value={visibility} onValueChange={(v) => setVisibility(v as TemplateVisibility)}>
              <SelectTrigger id="import-visibility">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TEMPLATE_VISIBILITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value} description={option.description}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="import-tags" className="text-xs font-medium text-muted-foreground">
            {t('templates.importDialog.tagsOptional')}
          </label>
          <Input id="import-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder={t('templates.importDialog.tagsPlaceholder')} />
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
