import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';

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

export function ViewXmlDialog({
  open,
  fileName,
  xml,
  error,
  onClose,
}: {
  open: boolean;
  fileName: string;
  xml: string | null;
  error: string | null;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="View XML"
      size="md"
      footer={
        <Button type="button" variant="outline" onClick={onClose}>
          Close
        </Button>
      }
    >
      <p className="-mt-1 mb-3 text-sm text-muted-foreground">{fileName}</p>
      {error ? (
        <Alert tone="error">{error}</Alert>
      ) : (
        <pre className="max-h-[60vh] overflow-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap">
          {xml ?? 'Loading…'}
        </pre>
      )}
    </Modal>
  );
}
