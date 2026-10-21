import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

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
  const { t } = useTranslation();
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
      setError(t('processModelDetail.addFile.duplicateName'));
      return;
    }
    if (kind === 'upload' && uploadText == null) {
      setError(t('processModelDetail.addFile.chooseFile'));
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
      setError(err instanceof Error ? err.message : t('processModelDetail.addFile.failed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('processModelDetail.files.addFile')}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="add-pm-file-form" disabled={submitting || !fileName.trim()}>
            {submitting ? t('processModelDetail.addFile.adding') : t('processModelDetail.files.addFile')}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        {t('processModelDetail.addFile.hint')}
      </p>
      <form id="add-pm-file-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          <span aria-hidden>{t('processModelDetail.addFile.type')}</span>
          <Select
            value={kind}
            onValueChange={(v) => {
              setKind(v as FileKind);
              setUploadText(null);
              setError(null);
            }}
          >
            <SelectTrigger aria-label={t('processModelDetail.addFile.fileType')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPED.map((row) => (
                <SelectItem key={row.value} value={row.value}>
                  {row.label}
                </SelectItem>
              ))}
              <SelectItem value="upload">{t('processModelDetail.addFile.upload')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          {t('processModelDetail.addFile.fileName')}
          <Input
            value={fileName}
            onChange={(e) => setFileName(e.target.value)}
            placeholder={typed ? `diagram${typed.suffix}` : 'notes.txt'}
            aria-label={t('processModelDetail.addFile.fileName')}
            required
          />
        </label>

        {kind === 'upload' ? (
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            {t('processModelDetail.addFile.file')}
            <input
              type="file"
              aria-label={t('processModelDetail.addFile.uploadFile')}
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
