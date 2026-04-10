import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useEffect, useState } from "react";
import TenantService, { Tenant } from "../services/TenantService";
import { TenantModalType } from "../enums/TenantModalType";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

interface TenantModalProps {
  open: boolean;
  type: TenantModalType;
  tenant: Tenant | null;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

const MAX_SLUG_LENGTH = 15;
const MAX_DISPLAY_NAME_LENGTH = 50;
const TENANT_SLUG_PATTERN = /^[A-Za-z0-9_-]+$/;

function validateTenantSlug(value: string): string {
  if (!value) {
    return "Tenant slug cannot be empty";
  }
  if (value.length > MAX_SLUG_LENGTH) {
    return `Tenant slug must be ${MAX_SLUG_LENGTH} characters or fewer`;
  }
  if (!TENANT_SLUG_PATTERN.test(value)) {
    return "Tenant slug can only contain letters, numbers, hyphens, and underscores";
  }
  return "";
}

function validateDisplayName(value: string): string {
  if (!value) {
    return "Tenant display name cannot be empty";
  }
  if (value.length > MAX_DISPLAY_NAME_LENGTH) {
    return `Tenant display name must be ${MAX_DISPLAY_NAME_LENGTH} characters or fewer`;
  }
  return "";
}

function getErrorMessage(error: any): string {
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return "";
}

export default function TenantModal({
  open,
  type,
  tenant,
  onClose,
  onSuccess,
}: TenantModalProps) {
  const [loading, setLoading] = useState(false);

  // Create State
  const [createRealmId, setCreateRealmId] = useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createRealmIdError, setCreateRealmIdError] = useState("");
  const [createDisplayNameError, setCreateDisplayNameError] = useState("");

  // Edit State
  const [editName, setEditName] = useState("");
  const [editNameError, setEditNameError] = useState("");
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (open) {
      if (type === TenantModalType.CREATE_TENANT) {
        setCreateRealmId("");
        setCreateDisplayName("");
      } else if (tenant && type === TenantModalType.EDIT_TENANT) {
        setEditName(tenant.name);
      }
    } else if (!open) {
      // Reset state when modal closes to prevent stale data
      setCreateRealmId("");
      setCreateDisplayName("");
      setEditName("");
    }
    setCreateRealmIdError("");
    setCreateDisplayNameError("");
    setEditNameError("");
    setSubmitError("");
  }, [open, tenant, type]);

  const handleSubmit = async () => {
    let hasValidationError = false;
    setCreateRealmIdError("");
    setCreateDisplayNameError("");
    setEditNameError("");
    setSubmitError("");

    if (type === TenantModalType.CREATE_TENANT) {
      const trimmedRealmId = createRealmId.trim();
      const trimmedDisplayName = createDisplayName.trim();
      const realmIdError = validateTenantSlug(trimmedRealmId);
      const displayNameError = validateDisplayName(trimmedDisplayName);
      if (realmIdError) {
        setCreateRealmIdError(realmIdError);
        hasValidationError = true;
      }
      if (displayNameError) {
        setCreateDisplayNameError(displayNameError);
        hasValidationError = true;
      }
    } else if (type === TenantModalType.EDIT_TENANT) {
      if (!tenant) return;
      const trimmedName = editName.trim();
      const editError = validateDisplayName(trimmedName);
      if (editError) {
        setEditNameError(editError);
        hasValidationError = true;
      }
    }

    if (hasValidationError) {
      return;
    }

    setLoading(true);
    try {
      if (type === TenantModalType.CREATE_TENANT) {
        await TenantService.createTenant({
          realm_id: createRealmId.trim(),
          display_name: createDisplayName.trim(),
        });
      } else if (type === TenantModalType.EDIT_TENANT) {
        if (!tenant) return;
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
      onSuccess(
        type === TenantModalType.CREATE_TENANT
          ? "Tenant created successfully."
          : "Tenant updated successfully.",
      );
      onClose();
    } catch (err: any) {
      const errorMessage = getErrorMessage(err);
      if (
        type === TenantModalType.CREATE_TENANT &&
        errorMessage &&
        (errorMessage.toLowerCase().includes("already exists") ||
          errorMessage.toLowerCase().includes("conflict"))
      ) {
        setCreateRealmIdError("Tenant slug already exists");
        return;
      }
      const action =
        type === TenantModalType.CREATE_TENANT
          ? "create"
          : type === TenantModalType.EDIT_TENANT
            ? "update"
            : "delete";
      setSubmitError(errorMessage || `Failed to ${action} tenant. Please try again.`);
    } finally {
      setLoading(false);
    }
  };

  const isCreate = type === TenantModalType.CREATE_TENANT;
  const isDelete = type === TenantModalType.DELETE_TENANT;
  const title = isDelete ? "Delete Tenant" : isCreate ? "Add Tenant" : "Edit Tenant";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="tenant-modal-dialog"
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
            {submitError && (
              <Alert severity="error" data-testid="tenant-modal-error">
                {submitError}
              </Alert>
            )}
            {isCreate ? (
              <>
                <TextField
                  label="Realm Slug"
                  fullWidth
                  value={createRealmId}
                  onChange={(e) => {
                    setCreateRealmId(e.target.value);
                    if (createRealmIdError) {
                      setCreateRealmIdError("");
                    }
                    if (submitError) {
                      setSubmitError("");
                    }
                  }}
                  disabled={loading}
                  error={Boolean(createRealmIdError)}
                  helperText={createRealmIdError}
                  inputProps={{ maxLength: MAX_SLUG_LENGTH }}
                  data-testid="tenant-realm-id-input"
                />
                <TextField
                  label="Display Name"
                  fullWidth
                  value={createDisplayName}
                  onChange={(e) => {
                    setCreateDisplayName(e.target.value);
                    if (createDisplayNameError) {
                      setCreateDisplayNameError("");
                    }
                    if (submitError) {
                      setSubmitError("");
                    }
                  }}
                  disabled={loading}
                  error={Boolean(createDisplayNameError)}
                  helperText={createDisplayNameError}
                  inputProps={{ maxLength: MAX_DISPLAY_NAME_LENGTH }}
                  data-testid="tenant-display-name-input"
                />
              </>
            ) : (
              <TextField
                label="Name"
                fullWidth
                value={editName}
                onChange={(e) => {
                  setEditName(e.target.value);
                  if (editNameError) {
                    setEditNameError("");
                  }
                  if (submitError) {
                    setSubmitError("");
                  }
                }}
                disabled={loading}
                error={Boolean(editNameError)}
                helperText={editNameError}
                inputProps={{ maxLength: MAX_DISPLAY_NAME_LENGTH }}
                data-testid="tenant-name-input"
              />
            )}
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
          data-testid="tenant-modal-cancel-button"
          onClick={onClose}
          disabled={loading}
          variant="outlined"
          autoFocus={isDelete}
        >
          Cancel
        </Button>
        <Button
          data-testid="tenant-modal-submit-button"
          onClick={handleSubmit}
          variant="contained"
          color={isDelete ? "error" : "primary"}
          autoFocus={!isDelete}
          disabled={loading}
        >
          {loading ? "Processing..." : isDelete ? "Delete" : isCreate ? "Create" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
