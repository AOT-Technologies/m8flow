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
  existingTenants?: Tenant[];
  onClose: () => void;
  onSuccess: (
    message: string,
    tenantUpdates?: Partial<Tenant>,
    createdTenant?: Tenant,
  ) => void;
}

const MAX_DISPLAY_NAME_LENGTH = 50;
const GENERATED_TENANT_ALIAS_FALLBACK = "tenant";

function validateDisplayName(value: string): string {
  if (!value) {
    return "organization_name_cannot_be_empty";
  }
  if (value.length > MAX_DISPLAY_NAME_LENGTH) {
    return "organization_name_max_length";
  }
  return "";
}

function generateTenantAliasBase(name: string): string {
  const normalizedName = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const sanitizedAlias = normalizedName
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");

  return sanitizedAlias || GENERATED_TENANT_ALIAS_FALLBACK;
}

function generateUniqueTenantAlias(name: string, existingTenants: Tenant[]): string {
  const baseAlias = generateTenantAliasBase(name);
  const existingAliases = new Set(
    existingTenants
      .map((existingTenant) => existingTenant.slug?.trim().toLowerCase())
      .filter((slug): slug is string => Boolean(slug)),
  );

  if (!existingAliases.has(baseAlias)) {
    return baseAlias;
  }

  let suffix = 2;
  while (existingAliases.has(`${baseAlias}-${suffix}`)) {
    suffix += 1;
  }
  return `${baseAlias}-${suffix}`;
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
  existingTenants = [],
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
  const [createTenantName, setCreateTenantName] = useState("");
  const [createTenantNameError, setCreateTenantNameError] = useState("");

  // Edit State
  const [editName, setEditName] = useState("");
  const [editNameError, setEditNameError] = useState("");
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (open) {
      if (type === TenantModalType.CREATE_TENANT) {
        setCreateTenantName("");
      } else if (tenant && type === TenantModalType.EDIT_TENANT) {
        setEditName(tenant.name);
      }
    } else if (!open) {
      // Reset state when modal closes to prevent stale data
      setCreateTenantName("");
      setEditName("");
    }
    setCreateTenantNameError("");
    setEditNameError("");
    setSubmitError("");
  }, [open, tenant, type]);

  const handleSubmit = async () => {
    let hasValidationError = false;
    setCreateTenantNameError("");
    setEditNameError("");
    setSubmitError("");

    if (type === TenantModalType.CREATE_TENANT) {
      const trimmedTenantName = createTenantName.trim();
      const tenantNameError = validateDisplayName(trimmedTenantName);
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
      let createdTenant: Tenant | undefined;
      if (type === TenantModalType.CREATE_TENANT) {
        const generatedTenantAlias = generateUniqueTenantAlias(
          createTenantName.trim(),
          existingTenants,
        );
        const createdTenantResponse = await TenantService.createTenant({
          slug: generatedTenantAlias,
          name: createTenantName.trim(),
        });
        createdTenant = {
          id: createdTenantResponse.id,
          slug: createdTenantResponse.alias,
          name: createdTenantResponse.name,
          status: "ACTIVE",
          createdBy: "",
          modifiedBy: "",
          createdAtInSeconds: 0,
          updatedAtInSeconds: 0,
        };
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
              "Tenant created successfully.",
            )
          : translate(
              "organization_updated_successfully",
              "Tenant updated successfully.",
            ),
        type === TenantModalType.EDIT_TENANT
          ? { name: editName.trim() }
          : undefined,
        createdTenant,
      );
      onClose();
    } catch (err: any) {
      const errorMessage = getErrorMessage(err);
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
            `Failed to ${action} tenant. Please try again.`,
          ),
      );
    } finally {
      setLoading(false);
    }
  };

  const isCreate = type === TenantModalType.CREATE_TENANT;
  const isDelete = type === TenantModalType.DELETE_TENANT;
  const title = isDelete
    ? translate("delete_organization", "Delete Tenant")
    : isCreate
      ? translate("add_organization", "Add Tenant")
      : translate("edit_organization", "Edit Tenant");

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
                "Are you sure you want to delete the tenant",
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
              <TextField
                label={translate("organization_name", "Tenant Name")}
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
            ) : (
              <TextField
                label={translate("organization_name", "Tenant Name")}
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
