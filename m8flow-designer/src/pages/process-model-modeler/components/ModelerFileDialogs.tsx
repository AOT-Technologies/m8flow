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
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next) onStay(); }}
      title="Unsaved changes"
      description="Leave this file? Unsaved edits will be lost."
      cancelLabel="Stay"
      confirmLabel="Leave"
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
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => { if (!next && !submitting) onCancel(); }}
      title="Delete file"
      description={`Delete ${fileName}? This cannot be undone. You will return to the process-model overview.`}
      confirmLabel={submitting ? 'Deleting…' : 'Delete'}
      pending={submitting}
      onConfirm={onConfirm}
    />
  );
}
