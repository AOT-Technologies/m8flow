import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from "@mui/material";
import { useEffect, useState } from "react";
import TenantService, {
  Tenant,
  EditableTenantStatus,
} from "../services/TenantService";
import { TenantModalType } from "../enums/TenantModalType";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

interface TenantModalProps {
  open: boolean;
  type: TenantModalType;
  tenant: Tenant | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function TenantModal({
  open,
  type,
  tenant,
  onClose,
  onSuccess,
}: TenantModalProps) {
  const [loading, setLoading] = useState(false);

  // Edit State
  const [editName, setEditName] = useState("");
  const [editStatus, setEditStatus] = useState<EditableTenantStatus>("ACTIVE");

  useEffect(() => {
    if (open && tenant) {
      if (type === TenantModalType.EDIT_TENANT) {
        setEditName(tenant.name);
        setEditStatus(tenant.status === "DELETED" ? "INACTIVE" : tenant.status);
      }
    } else if (!open) {
      // Reset state when modal closes to prevent stale data
      setEditName("");
      setEditStatus("ACTIVE");
    }
  }, [open, tenant, type]);

  const handleSubmit = async () => {
    if (!tenant) return;

    // Validate name for edit operation
    if (type === TenantModalType.EDIT_TENANT) {
      const trimmedName = editName.trim();
      if (!trimmedName) {
        alert("Tenant name cannot be empty");
        return;
      }
    }

    setLoading(true);
    try {
      if (type === TenantModalType.EDIT_TENANT) {
        // TODO: Phase 2 - Only updating name for now. Status change will be added in Phase 2
        await TenantService.updateTenant(tenant.id, {
          name: editName.trim(),
          // status: editStatus, // Phase 2 feature
        });
      }
      // TODO: Phase 2 - Delete functionality will be implemented in Phase 2
      // else if (type === TenantModalType.DELETE_TENANT) {
      //   await TenantService.deleteTenant(tenant.id);
      // }
      onSuccess();
      onClose();
    } catch (err: any) {
      const action = type === TenantModalType.EDIT_TENANT ? "update" : "delete";
      alert(err.message || `Failed to ${action} tenant. Please try again.`);
    } finally {
      setLoading(false);
    }
  };

  const isDelete = type === TenantModalType.DELETE_TENANT;
  const title = isDelete ? "Delete Tenant" : "Edit Tenant";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      onKeyDown={(e) => {
        // Prevent Enter from triggering delete
        if (e.key === "Enter" && isDelete) {
          e.preventDefault();
        }
      }}
    >
      <DialogTitle
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          fontSize: "1.5rem",
          fontWeight: 600,
        }}
      >
        {isDelete && (
          <WarningAmberIcon sx={{ color: "error.main", fontSize: "1.75rem" }} />
        )}
        {title}
      </DialogTitle>
      <DialogContent>
        {isDelete ? (
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <DialogContentText>
              Are you sure you want to delete the tenant{" "}
              <strong>"{tenant?.name}"</strong>?
            </DialogContentText>

            <DialogContentText
              sx={{ color: "error.main", fontWeight: 500, fontSize: "0.9rem" }}
            >
              This action cannot be undone.
            </DialogContentText>
          </Stack>
        ) : (
          <Stack spacing={3} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              fullWidth
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              disabled={loading}
            />
            {/* TODO: Phase 2 - Status change functionality will be implemented in Phase 2 */}
            {/* <FormControl fullWidth>
              <InputLabel>Status</InputLabel>
              <Select
                value={editStatus}
                label="Status"
                onChange={(e) =>
                  setEditStatus(e.target.value as EditableTenantStatus)
                }
                disabled={loading}
              >
                <MenuItem value="ACTIVE">Active</MenuItem>
                <MenuItem value="INACTIVE">Inactive</MenuItem>
              </Select>
            </FormControl> */}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button
          onClick={onClose}
          disabled={loading}
          variant="outlined"
          autoFocus={isDelete}
        >
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          color={isDelete ? "error" : "primary"}
          autoFocus={!isDelete}
          disabled={loading}
        >
          {loading ? "Processing..." : isDelete ? "Delete" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
