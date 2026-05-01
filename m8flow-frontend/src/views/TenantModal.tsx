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
import { useTranslation } from "react-i18next";
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
    return "organization_alias_cannot_be_empty";
  }
  if (value.length > MAX_SLUG_LENGTH) {
    return "organization_alias_max_length";
  }
  if (!TENANT_SLUG_PATTERN.test(value)) {
    return "organization_alias_invalid_pattern";
  }
  return "";
}

function validateDisplayName(value: string): string {
  if (!value) {
    return "organization_name_cannot_be_empty";
  }
  if (value.length > MAX_DISPLAY_NAME_LENGTH) {
    return "organization_name_max_length";
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
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const translate = (
    key: string,
    fallback: string,
    options?: Record<string, unknown>,
  ) => {
    const translated = t(key, options);
    return translated === key ? fallback : translated;
  };

  // Create State
  const [createTenantAlias, setCreateTenantAlias] = useState("");
  const [createTenantName, setCreateTenantName] = useState("");
  const [createTenantAliasError, setCreateTenantAliasError] = useState("");
  const [createTenantNameError, setCreateTenantNameError] = useState("");

  // Edit State
  const [editName, setEditName] = useState("");
  const [editNameError, setEditNameError] = useState("");
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (open) {
      if (type === TenantModalType.CREATE_TENANT) {
        setCreateTenantAlias("");
        setCreateTenantName("");
      } else if (tenant && type === TenantModalType.EDIT_TENANT) {
        setEditName(tenant.name);
      }
    } else if (!open) {
      // Reset state when modal closes to prevent stale data
      setCreateTenantAlias("");
      setCreateTenantName("");
      setEditName("");
    }
    setCreateTenantAliasError("");
    setCreateTenantNameError("");
    setEditNameError("");
    setSubmitError("");
  }, [open, tenant, type]);

  const handleSubmit = async () => {
    let hasValidationError = false;
    setCreateTenantAliasError("");
    setCreateTenantNameError("");
    setEditNameError("");
    setSubmitError("");

    if (type === TenantModalType.CREATE_TENANT) {
      const trimmedTenantAlias = createTenantAlias.trim();
      const trimmedTenantName = createTenantName.trim();
      const tenantAliasError = validateTenantSlug(trimmedTenantAlias);
      const tenantNameError = validateDisplayName(trimmedTenantName);
      if (tenantAliasError) {
        setCreateTenantAliasError(t(tenantAliasError, { count: MAX_SLUG_LENGTH }));
        hasValidationError = true;
      }
      if (tenantNameError) {
        setCreateTenantNameError(t(tenantNameError, { count: MAX_DISPLAY_NAME_LENGTH }));
        hasValidationError = true;
      }
    } else if (type === TenantModalType.EDIT_TENANT) {
      if (!tenant) return;
      const trimmedName = editName.trim();
      const editError = validateDisplayName(trimmedName);
      if (editError) {
        setEditNameError(t(editError, { count: MAX_DISPLAY_NAME_LENGTH }));
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
          slug: createTenantAlias.trim(),
          name: createTenantName.trim(),
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
          ? translate(
              "organization_created_successfully",
              "Organization created successfully.",
            )
          : translate(
              "organization_updated_successfully",
              "Organization updated successfully.",
            ),
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
        setCreateTenantAliasError(
          translate(
            "organization_alias_already_exists",
            "Organization alias already exists",
          ),
        );
        return;
      }
      const action =
        type === TenantModalType.CREATE_TENANT
          ? "create"
          : type === TenantModalType.EDIT_TENANT
            ? "update"
            : "delete";
      setSubmitError(
        errorMessage ||
          translate(
            `failed_to_${action}_organization`,
            `Failed to ${action} organization. Please try again.`,
          ),
      );
    } finally {
      setLoading(false);
    }
  };

  const isCreate = type === TenantModalType.CREATE_TENANT;
  const isDelete = type === TenantModalType.DELETE_TENANT;
  const title = isDelete
    ? translate("delete_organization", "Delete Organization")
    : isCreate
      ? translate("add_organization", "Add Organization")
      : translate("edit_organization", "Edit Organization");

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
              {translate(
                "are_you_sure_you_want_to_delete_organization",
                "Are you sure you want to delete the organization",
              )}{" "}
              <strong>"{tenant?.name}"</strong>?
            </DialogContentText>

            <DialogContentText
              sx={{ color: "error.main", fontWeight: 500, fontSize: "0.9rem" }}
            >
              {t("action_cannot_be_undone")}
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
                  label={translate("organization_alias", "Organization Alias")}
                  fullWidth
                  value={createTenantAlias}
                  onChange={(e) => {
                    setCreateTenantAlias(e.target.value);
                    if (createTenantAliasError) {
                      setCreateTenantAliasError("");
                    }
                    if (submitError) {
                      setSubmitError("");
                    }
                  }}
                  disabled={loading}
                  error={Boolean(createTenantAliasError)}
                  helperText={createTenantAliasError}
                  inputProps={{ maxLength: MAX_SLUG_LENGTH }}
                  data-testid="tenant-realm-id-input"
                />
                <TextField
                  label={translate("organization_name", "Organization Name")}
                  fullWidth
                  value={createTenantName}
                  onChange={(e) => {
                    setCreateTenantName(e.target.value);
                    if (createTenantNameError) {
                      setCreateTenantNameError("");
                    }
                    if (submitError) {
                      setSubmitError("");
                    }
                  }}
                  disabled={loading}
                  error={Boolean(createTenantNameError)}
                  helperText={createTenantNameError}
                  inputProps={{ maxLength: MAX_DISPLAY_NAME_LENGTH }}
                  data-testid="tenant-display-name-input"
                />
              </>
            ) : (
              <TextField
                label={translate("organization_name", "Organization Name")}
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
          {t("cancel")}
        </Button>
        <Button
          data-testid="tenant-modal-submit-button"
          onClick={handleSubmit}
          variant="contained"
          color={isDelete ? "error" : "primary"}
          autoFocus={!isDelete}
          disabled={loading}
        >
          {loading ? t("processing") : isDelete ? t("delete") : isCreate ? t("create") : t("save")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
