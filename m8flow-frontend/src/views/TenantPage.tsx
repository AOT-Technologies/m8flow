import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Box,
  ButtonBase,
  Typography,
  Paper,
  Stack,
  TextField,
  InputAdornment,
  IconButton,
  TableSortLabel,
  Chip,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  Button,
  Snackbar,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import EditIcon from "@mui/icons-material/Edit";
import ClearIcon from "@mui/icons-material/Clear";
import AddIcon from "@mui/icons-material/Add";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";
import { Tenant } from "../services/TenantService";
import { useTenants } from "../hooks/useTenants";
import UserService from "../services/UserService";
import TenantModal from "./TenantModal";
import TenantRoleDialog from "./TenantRoleDialog";
import { TenantModalType } from "../enums/TenantModalType";

const STATUS_COLORS = {
  ACTIVE: "success",
  INACTIVE: "warning",
  DELETED: "error",
} as const;
const TENANT_EXPANDED_ROW_BACKGROUND_COLOR = "#DDF4F1";
const TENANT_LIST_GRID_TEMPLATE_COLUMNS = {
  xs: "1fr",
  md: "minmax(220px, 2fr) minmax(220px, 2fr) minmax(110px, auto) 40px",
} as const;

type SortField = "name" | "slug";
type SortDirection = "asc" | "desc";
type SearchType = "name" | "slug";

export default function TenantPage() {
  const { ability, permissionsLoaded } = usePermissionFetcher({
    "/m8flow/tenant-realms": ["POST"],
  });
  const {
    data: tenants = [],
    isLoading: loading,
    error: queryError,
    refetch,
  } = useTenants(true);
  const canCreateTenant =
    permissionsLoaded && ability.can("POST", "/m8flow/tenant-realms");
  const { t } = useTranslation();
  const translate = (
    key: string,
    fallback: string,
    options?: Record<string, unknown>,
  ) => {
    const translated = t(key, options);
    return translated === key ? fallback : translated;
  };
  const organizationAliasLabel = translate(
    "organization_alias",
    "Tenant Alias",
  );
  const organizationNameLabel = translate(
    "organization_name",
    "Tenant Name",
  );

  // Search and filter states
  const [searchQuery, setSearchQuery] = useState("");
  const [searchType, setSearchType] = useState<SearchType>("name");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Sorting states
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<TenantModalType>(
    TenantModalType.EDIT_TENANT,
  );
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [expandedTenantId, setExpandedTenantId] = useState<string | null>(null);
  const [pendingExpandedTenantId, setPendingExpandedTenantId] = useState<string | null>(null);
  const [createdTenantPreview, setCreatedTenantPreview] = useState<Tenant | null>(null);
  const [successMessage, setSuccessMessage] = useState("");

  const toggleTenantExpansion = (tenantId: string) => {
    setExpandedTenantId((currentTenantId) =>
      currentTenantId === tenantId ? null : tenantId,
    );
  };

  // Handle edit
  const handleEdit = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    setModalType(TenantModalType.EDIT_TENANT);
    setIsModalOpen(true);
  };

  const handleCreate = () => {
    setSelectedTenant(null);
    setPendingExpandedTenantId(null);
    setCreatedTenantPreview(null);
    setModalType(TenantModalType.CREATE_TENANT);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTenant(null);
  };

  const handleModalSuccess = (
    message: string,
    tenantUpdates?: Partial<Tenant>,
    createdTenant?: Tenant,
  ) => {
    if (
      modalType === TenantModalType.EDIT_TENANT
      && selectedTenant
      && typeof tenantUpdates?.name === "string"
      && tenantUpdates.name.trim()
    ) {
      UserService.rememberTenantDisplayName({
        id: selectedTenant.id,
        alias: selectedTenant.slug,
        name: tenantUpdates.name.trim(),
      });
    }
    if (modalType === TenantModalType.CREATE_TENANT && createdTenant) {
      setCreatedTenantPreview(createdTenant);
      setPendingExpandedTenantId(createdTenant.id);
    }
    setSuccessMessage(message);
    refetch();
  };

  useEffect(() => {
    if (!isModalOpen && pendingExpandedTenantId) {
      setExpandedTenantId(pendingExpandedTenantId);
      setPendingExpandedTenantId(null);
    }
  }, [isModalOpen, pendingExpandedTenantId]);

  const tenantsWithPendingCreate = useMemo(() => {
    if (!createdTenantPreview) {
      return tenants;
    }

    const hasCreatedTenant = tenants.some(
      (tenant) => tenant.id === createdTenantPreview.id,
    );

    if (hasCreatedTenant) {
      return tenants;
    }

    return [createdTenantPreview, ...tenants];
  }, [createdTenantPreview, tenants]);

  useEffect(() => {
    if (
      createdTenantPreview
      && tenants.some((tenant) => tenant.id === createdTenantPreview.id)
    ) {
      setCreatedTenantPreview(null);
    }
  }, [createdTenantPreview, tenants]);

  // Filter and search logic
  const filteredAndSortedTenants = useMemo(() => {
    let filtered = [...tenantsWithPendingCreate];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((tenant) => {
        if (searchType === "name") {
          return tenant.name.toLowerCase().includes(query);
        } else {
          return tenant.slug.toLowerCase().includes(query);
        }
      });
    }

    // Apply status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter((tenant) => tenant.status === statusFilter);
    }

    // Apply sorting
    filtered.sort((a, b) => {
      const aValue = a[sortField].toLowerCase();
      const bValue = b[sortField].toLowerCase();

      if (sortDirection === "asc") {
        return aValue.localeCompare(bValue);
      } else {
        return bValue.localeCompare(aValue);
      }
    });

    return filtered;
  }, [
    tenantsWithPendingCreate,
    searchQuery,
    searchType,
    statusFilter,
    sortField,
    sortDirection,
  ]);

  useEffect(() => {
    if (
      expandedTenantId
      && !filteredAndSortedTenants.some((tenant) => tenant.id === expandedTenantId)
    ) {
      setExpandedTenantId(null);
    }
  }, [expandedTenantId, filteredAndSortedTenants]);

  // Handle sort
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  // Clear all filters
  const clearFilters = () => {
    setSearchQuery("");
    setSearchType("name");
    setStatusFilter("all");
    setSortField("name");
    setSortDirection("asc");
  };

  const hasActiveFilters = searchQuery || statusFilter !== "all";

  return (
    <Box sx={{ padding: 3 }}>
      <Stack spacing={3}>
        {/* Header */}
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <Box>
            <Typography
              variant="h4"
              component="h1"
              style={{ fontWeight: "bold", fontSize: "24px" }}
            >
              {translate(
                "organization_management",
                "Tenant Management",
              )}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {translate(
                "organization_management_description",
                "Manage the Keycloak tenants that back access in Keycloak.",
              )}
            </Typography>
          </Box>
          {canCreateTenant && (
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreate}
              data-testid="tenant-add-button"
            >
              {translate("add_organization", "Add Tenant")}
            </Button>
          )}
        </Box>

        {/* Filters Section */}
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Box
              sx={{
                display: "flex",
                gap: 2,
                flexWrap: "wrap",
                alignItems: "flex-end",
              }}
            >
              {/* Search Bar */}
              <FormControl sx={{ minWidth: 150 }}>
                <InputLabel size="small">{t('search_by')}</InputLabel>
                <Select
                  size="small"
                  value={searchType}
                  label={t('search_by')}
                  data-testid="tenant-search-type-select"
                  onChange={(e) => setSearchType(e.target.value as SearchType)}
                >
                  <MenuItem value="name">{organizationNameLabel}</MenuItem>
                  <MenuItem value="slug">{organizationAliasLabel}</MenuItem>
                </Select>
              </FormControl>

              <TextField
                size="small"
                placeholder={t('search_by_placeholder', {
                  type:
                    searchType === 'name'
                      ? organizationNameLabel.toLowerCase()
                      : organizationAliasLabel.toLowerCase(),
                })}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="tenant-search-input"
                sx={{ flexGrow: 1, minWidth: 300 }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                  endAdornment: searchQuery && (
                    <InputAdornment position="end">
                      <IconButton
                        size="small"
                        onClick={() => setSearchQuery("")}
                      >
                        <ClearIcon fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />

              {/* Status Filter */}
              <FormControl sx={{ minWidth: 200 }}>
                <InputLabel size="small">{t('filter_by_status')}</InputLabel>
                <Select
                  size="small"
                  value={statusFilter}
                  label={t('filter_by_status')}
                  data-testid="tenant-status-filter-select"
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <MenuItem value="all">{t('all')}</MenuItem>
                  <MenuItem value="ACTIVE">{t('active')}</MenuItem>
                  <MenuItem value="INACTIVE">{t('inactive')}</MenuItem>
                  {/* <MenuItem value="DELETED">Deleted</MenuItem> */} {/*TODO: Phase 2 - Delete functionality will be implemented in Phase 2*/}
                </Select>
              </FormControl>
            </Box>

            {/* Filter Summary */}
            <Typography variant="caption" color="text.secondary">
              {translate("showing_organizations_count", "Showing {{filtered}} of {{total}} tenant(s)", {
                filtered: filteredAndSortedTenants.length,
                total: tenantsWithPendingCreate.length,
              })}
            </Typography>
          </Stack>
        </Paper>

        {/* Accordion List */}
        <Paper>
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
              <CircularProgress />
            </Box>
          ) : queryError ? (
            <Alert severity="error" sx={{ m: 2 }}>
              {queryError.message}
            </Alert>
          ) : filteredAndSortedTenants.length === 0 ? (
            <Box sx={{ p: 4, textAlign: "center" }}>
              <Typography color="text.secondary">
                {searchQuery || statusFilter !== "all"
                  ? translate(
                      "no_organizations_matching_filters",
                      "No tenants found matching your filters",
                    )
                  : translate(
                      "no_organizations_available",
                      "No tenants available",
                    )}
              </Typography>
            </Box>
          ) : (
            <Box data-testid="tenant-table">
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: TENANT_LIST_GRID_TEMPLATE_COLUMNS,
                  gap: 2,
                  px: 2,
                  py: 2,
                  alignItems: "center",
                  borderBottom: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Box>
                  <TableSortLabel
                    active={sortField === "name"}
                    direction={sortField === "name" ? sortDirection : "asc"}
                    onClick={() => handleSort("name")}
                  >
                    {organizationNameLabel}
                  </TableSortLabel>
                </Box>
                <Box>
                  <TableSortLabel
                    active={sortField === "slug"}
                    direction={sortField === "slug" ? sortDirection : "asc"}
                    onClick={() => handleSort("slug")}
                  >
                    {organizationAliasLabel}
                  </TableSortLabel>
                </Box>
                <Typography variant="body2">{t("status")}</Typography>
                <Box />
              </Box>

              {filteredAndSortedTenants.map((tenant, index) => {
                const isExpanded = expandedTenantId === tenant.id;

                return (
                  <Box
                    component="section"
                    key={tenant.id}
                    data-testid={`tenant-row-${tenant.id}`}
                    sx={{
                      borderBottom:
                        index === filteredAndSortedTenants.length - 1
                          ? "none"
                          : "1px solid",
                      borderColor: "divider",
                    }}
                  >
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: {
                          xs: "1fr auto",
                          md: "minmax(220px, 2fr) minmax(220px, 2fr) minmax(110px, auto) 40px",
                        },
                        gap: 2,
                        px: 2,
                        py: 1,
                        alignItems: "center",
                        backgroundColor: isExpanded
                          ? TENANT_EXPANDED_ROW_BACKGROUND_COLOR
                          : "transparent",
                        transition: "background-color 0.2s ease",
                      }}
                    >
                      <ButtonBase
                        onClick={() => toggleTenantExpansion(tenant.id)}
                        data-testid={`tenant-accordion-summary-${tenant.id}`}
                        aria-expanded={isExpanded}
                        aria-controls={`tenant-accordion-details-${tenant.id}`}
                        sx={{
                          display: "grid",
                          gridColumn: {
                            xs: "1 / span 1",
                            md: "1 / span 3",
                          },
                          gridTemplateColumns: {
                            xs: "1fr",
                            md: "minmax(220px, 2fr) minmax(220px, 2fr) minmax(110px, auto)",
                          },
                          gap: 2,
                          alignItems: "center",
                          justifyItems: "start",
                          textAlign: "left",
                          width: "100%",
                          borderRadius: 1,
                          px: 0,
                          py: 1,
                        }}
                      >
                        <Typography
                          variant="body2"
                          fontWeight={700}
                          data-testid={`tenant-name-${tenant.id}`}
                        >
                          {tenant.name}
                        </Typography>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          data-testid={`tenant-slug-${tenant.id}`}
                        >
                          {tenant.slug}
                        </Typography>
                        <Box>
                          <Chip
                            label={tenant.status}
                            color={STATUS_COLORS[tenant.status]}
                            size="small"
                            data-testid={`tenant-status-${tenant.id}`}
                            sx={{
                              fontWeight: 600,
                              minWidth: 85,
                              fontSize: "0.75rem",
                            }}
                          />
                        </Box>
                      </ButtonBase>
                      <IconButton
                        size="small"
                        onClick={() => toggleTenantExpansion(tenant.id)}
                        data-testid={`tenant-accordion-toggle-${tenant.id}`}
                        aria-label={
                          isExpanded
                            ? `Collapse ${tenant.name}`
                            : `Expand ${tenant.name}`
                        }
                        aria-expanded={isExpanded}
                        aria-controls={`tenant-accordion-details-${tenant.id}`}
                      >
                        <ExpandMoreIcon
                          sx={{
                            transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                            transition: "transform 0.2s ease",
                          }}
                        />
                      </IconButton>
                    </Box>
                    {isExpanded ? (
                      <Box
                        data-testid={`tenant-accordion-details-${tenant.id}`}
                        id={`tenant-accordion-details-${tenant.id}`}
                        sx={{ px: 2, pb: 2, pt: 1.5 }}
                      >
                        <Stack
                          direction="row"
                          alignItems="center"
                          spacing={2}
                          useFlexGap
                          flexWrap="wrap"
                          sx={{ mb: 1.5 }}
                        >
                          <Typography
                            variant="body1"
                            color="text.secondary"
                            sx={{
                              flex: "1 1 480px",
                              minWidth: 0,
                            }}
                          >
                            {translate(
                              "tenant_group_management_description",
                              "Add existing users as members and manage groups and roles associated with this tenant.",
                            )}
                          </Typography>
                          <Button
                            variant="outlined"
                            size="small"
                            startIcon={<EditIcon />}
                            onClick={() => handleEdit(tenant)}
                            disabled={tenant.status === "DELETED"}
                            data-testid={`tenant-inline-edit-button-${tenant.id}`}
                            sx={{
                              flexShrink: 0,
                              marginLeft: "auto",
                            }}
                          >
                            {translate("edit_organization_name", "Edit Name")}
                          </Button>
                        </Stack>
                        <TenantRoleDialog
                          embedded
                          tenant={tenant}
                          onClose={() => undefined}
                          showDescription={false}
                        />
                      </Box>
                    ) : null}
                  </Box>
                );
              })}
            </Box>
          )}
        </Paper>
      </Stack>

      <TenantModal
        open={isModalOpen}
        type={modalType}
        tenant={selectedTenant}
        existingTenants={tenantsWithPendingCreate}
        onClose={handleCloseModal}
        onSuccess={handleModalSuccess}
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
