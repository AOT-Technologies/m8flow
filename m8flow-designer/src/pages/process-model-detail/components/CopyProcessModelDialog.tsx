import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type CopyProcessModelDialogProps = {
  open: boolean;
  onClose: () => void;
  defaultLeaf: string;
  defaultDisplayName: string;
  onCopied: (encodedProcessModelId: string) => void;
  onCopy: (input: { id: string; display_name: string }) => Promise<{ id: string }>;
};

export function CopyProcessModelDialog({
  open,
  onClose,
  defaultLeaf,
  defaultDisplayName,
  onCopied,
  onCopy,
}: CopyProcessModelDialogProps) {
  const { t } = useTranslation();
  const [processModelId, setProcessModelId] = useState(defaultLeaf);
  const [displayName, setDisplayName] = useState(defaultDisplayName);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setProcessModelId(defaultLeaf);
    setDisplayName(defaultDisplayName);
    setError(null);
  }, [open, defaultLeaf, defaultDisplayName]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!processModelId.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await onCopy({
        id: processModelId.trim(),
        display_name: displayName.trim(),
      });
      onCopied(result.id.split('/').join(':'));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('processModelDetail.copy.failed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('processModelDetail.copy.title')}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="copy-pm-form" disabled={submitting || !processModelId.trim()}>
            {submitting ? t('processModelDetail.copy.copying') : t('processModelDetail.copy.title')}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        {t('processModelDetail.copy.hint')}
      </p>
      <form id="copy-pm-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="copy-pm-id" className="text-xs font-medium text-muted-foreground">
            {t('processModelDetail.copy.processModelId')}
          </label>
          <Input
            id="copy-pm-id"
            value={processModelId}
            onChange={(e) => setProcessModelId(e.target.value)}
            placeholder="invoice-approval-copy"
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="copy-pm-name" className="text-xs font-medium text-muted-foreground">
            {t('processModelDetail.displayName')}
          </label>
          <Input
            id="copy-pm-name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={t('processModelDetail.copy.displayNamePlaceholder')}
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
