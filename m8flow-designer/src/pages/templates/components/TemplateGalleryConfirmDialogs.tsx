import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';

export function TemplateDeleteConfirmDialog({
  open,
  templateName,
  isPublished,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  templateName: string;
  isPublished: boolean;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const description = isPublished
    ? t('templates.deleteDialog.softDelete', { name: templateName })
    : t('templates.deleteDialog.hardDelete', { name: templateName });

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title={t('templates.deleteDialog.title')}
      description={description}
      confirmLabel={submitting ? t('templates.deleteDialog.deleting') : t('common.delete')}
      pending={submitting}
      onConfirm={onConfirm}
    />
  );
}

export function TemplateRestoreConfirmDialog({
  open,
  templateName,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  templateName: string;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title={t('templates.restoreDialog.title')}
      description={t('templates.restoreDialog.description', { name: templateName })}
      confirmLabel={submitting ? t('templates.restoreDialog.restoring') : t('templates.restoreDialog.restore')}
      tone="default"
      pending={submitting}
      onConfirm={onConfirm}
    />
  );
}
