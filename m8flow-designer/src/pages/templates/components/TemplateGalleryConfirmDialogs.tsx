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
  const description = isPublished
    ? `"${templateName}" will be soft-deleted and can be restored from the Deleted tab.`
    : `"${templateName}" will be permanently deleted.`;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title="Delete template?"
      description={description}
      confirmLabel={submitting ? 'Deleting…' : 'Delete'}
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
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title="Restore template?"
      description={`"${templateName}" will be restored and become active again.`}
      confirmLabel={submitting ? 'Restoring…' : 'Restore'}
      tone="default"
      pending={submitting}
      onConfirm={onConfirm}
    />
  );
}
