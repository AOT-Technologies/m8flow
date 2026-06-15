import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
  Box,
} from '@mui/material';
import WarningIcon from '@mui/icons-material/Warning';
import { useTranslation } from 'react-i18next';

export interface TemplateDeleteConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  templateName: string;
  isPublished: boolean;
}

export default function TemplateDeleteConfirmDialog({
  open,
  onClose,
  onConfirm,
  templateName,
  isPublished,
}: TemplateDeleteConfirmDialogProps) {
  const { t } = useTranslation();

  const description = isPublished
    ? t("delete_template_published_modal_body", {
        name: templateName,
        defaultValue: `"${templateName}" will be soft-deleted and can be restored from the Deleted tab.`,
      })
    : t("delete_template_draft_modal_body", {
        name: templateName,
        defaultValue: `"${templateName}" will be permanently deleted.`,
      });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby="delete-template-dialog-title"
      aria-describedby="delete-template-dialog-description"
      data-testid="delete-template-confirm-dialog"
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle id="delete-template-dialog-title">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <WarningIcon color="warning" fontSize="small" />
          {t("delete_template_title", { defaultValue: "Delete template?" })}
        </Box>
      </DialogTitle>
      <DialogContent>
        <DialogContentText id="delete-template-dialog-description">
          {description}
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button
          onClick={onClose}
          color="primary"
          data-testid="delete-template-cancel-button"
        >
          {t("cancel")}
        </Button>
        <Button
          onClick={onConfirm}
          color="error"
          variant="contained"
          data-testid="delete-template-confirm-button"
        >
          {t("delete")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
 * Restore confirmation dialog (separate export)
 * ──────────────────────────────────────────────────────────────────────────── */

export interface TemplateRestoreConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  templateName: string;
}

export function TemplateRestoreConfirmDialog({
  open,
  onClose,
  onConfirm,
  templateName,
}: TemplateRestoreConfirmDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby="restore-template-dialog-title"
      aria-describedby="restore-template-dialog-description"
      data-testid="restore-template-confirm-dialog"
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle id="restore-template-dialog-title">
        {t("restore_template_title", { defaultValue: "Restore template?" })}
      </DialogTitle>
      <DialogContent>
        <DialogContentText id="restore-template-dialog-description">
          {t("restore_template_modal_body", {
            name: templateName,
            defaultValue: `"${templateName}" will be restored and become active again.`,
          })}
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button
          onClick={onClose}
          color="primary"
          data-testid="restore-template-cancel-button"
        >
          {t("cancel")}
        </Button>
        <Button
          onClick={onConfirm}
          color="primary"
          variant="contained"
          data-testid="restore-template-confirm-button"
        >
          {t("restore", { defaultValue: "Restore" })}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
