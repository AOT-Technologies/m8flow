import EditIcon from "@mui/icons-material/Edit";
import { Alert, Box, Button, Snackbar, Stack, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TenantModalType } from "../enums/TenantModalType";
import UserService from "../services/UserService";
import type { OrganizationMembership } from "../services/UserService";
import type { Tenant } from "../services/TenantService";
import TenantModal from "./TenantModal";
import TenantRoleDialog from "./TenantRoleDialog";

export const tenantManagementPageHelpers = {
  reloadPage: () => window.location.reload(),
};

function fallbackTenant(identifier: string): Tenant {
  return {
    id: identifier,
    name: identifier,
    slug: identifier,
    status: "ACTIVE",
    createdBy: "",
    modifiedBy: "",
    createdAtInSeconds: 0,
    updatedAtInSeconds: 0,
  };
}

function tenantFromMembership(
  tenantIdentifier: string,
  memberships: OrganizationMembership[],
  fallbackName: string | null,
): Tenant {
  const matchingMembership =
    memberships.find((membership) => membership.id === tenantIdentifier)
    || memberships.find((membership) => membership.alias === tenantIdentifier)
    || memberships[0];

  if (!matchingMembership) {
    return {
      ...fallbackTenant(tenantIdentifier),
      name: fallbackName || tenantIdentifier,
    };
  }

  return {
    id: matchingMembership.id || tenantIdentifier,
    name: matchingMembership.name || fallbackName || matchingMembership.alias,
    slug: matchingMembership.alias,
    status: "ACTIVE",
    createdBy: "",
    modifiedBy: "",
    createdAtInSeconds: 0,
    updatedAtInSeconds: 0,
  };
}

export default function TenantManagementPage() {
  const { t } = useTranslation();
  const translate = (
    key: string,
    fallback: string,
    options?: Record<string, unknown>,
  ) => {
    const translated = t(key, options);
    return translated === key ? fallback : translated;
  };

  const currentTenantIdentifier = UserService.getTenantId();
  const currentTenantName = UserService.getTenantName();
  const tenantMemberships = UserService.getOrganizationMemberships();

  const initialTenant = useMemo(() => {
    if (!currentTenantIdentifier) {
      return null;
    }
    return tenantFromMembership(
      currentTenantIdentifier,
      tenantMemberships,
      currentTenantName,
    );
  }, [currentTenantIdentifier, currentTenantName, tenantMemberships]);

  const [tenant, setTenant] = useState<Tenant | null>(initialTenant);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  if (!tenant) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">
          {translate(
            "tenant_management_missing_tenant_context",
            "No active tenant context is available for tenant management.",
          )}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 2,
            flexWrap: "wrap",
          }}
        >
          <Box>
            <Typography
              variant="h4"
              component="h1"
              sx={{ fontWeight: "bold", fontSize: "24px" }}
            >
              {translate("tenant_management", "Tenant Management")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {translate(
                "tenant_group_management_description",
                "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
              )}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={<EditIcon />}
            onClick={() => setIsEditModalOpen(true)}
            data-testid="tenant-management-edit-button"
          >
            {translate("edit_organization", "Edit Tenant")}
          </Button>
        </Box>

        <TenantRoleDialog
          embedded
          tenant={tenant}
          onClose={() => undefined}
          showDescription={false}
        />
      </Stack>

      <TenantModal
        open={isEditModalOpen}
        type={TenantModalType.EDIT_TENANT}
        tenant={tenant}
        onClose={() => setIsEditModalOpen(false)}
        onSuccess={(message, tenantUpdates) => {
          setSuccessMessage(message);
          if (tenantUpdates?.name) {
            UserService.rememberTenantDisplayName({
              id: tenant.id,
              alias: tenant.slug,
              name: tenantUpdates.name,
            });
            setTenant((currentTenant) => (
              currentTenant
                ? { ...currentTenant, name: tenantUpdates.name || currentTenant.name }
                : currentTenant
            ));
          }
          tenantManagementPageHelpers.reloadPage();
        }}
      />

      <Snackbar
        open={Boolean(successMessage)}
        autoHideDuration={4000}
        onClose={() => setSuccessMessage("")}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
      >
        <Alert
          severity="success"
          onClose={() => setSuccessMessage("")}
          sx={{ width: "100%" }}
        >
          {successMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
}
