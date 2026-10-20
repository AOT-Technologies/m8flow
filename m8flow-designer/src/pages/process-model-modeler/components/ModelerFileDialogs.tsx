import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';

export function UnsavedChangesDialog({
  open,
  onStay,
  onLeave,
}: {
  open: boolean;
  onStay: () => void;
  onLeave: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next) onStay(); }}
      title={t('modeler.dialogs.unsavedTitle')}
      description={t('modeler.dialogs.unsavedDescription')}
      cancelLabel={t('modeler.dialogs.stay')}
      confirmLabel={t('modeler.dialogs.leave')}
      onConfirm={onLeave}
    />
  );
}

export function DeleteFileDialog({
  open,
  fileName,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  fileName: string;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title={t('modeler.dialogs.deleteTitle')}
      description={t('modeler.dialogs.deleteDescription', { fileName })}
      confirmLabel={submitting ? t('modeler.dialogs.deleting') : t('common.delete')}
      pending={submitting}
      onConfirm={onConfirm}
    />
  );
}
