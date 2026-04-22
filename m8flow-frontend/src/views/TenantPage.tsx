import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Box,
  Typography,
  Paper,
  Stack,
  TextField,
  InputAdornment,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Chip,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Tooltip,
  CircularProgress,
  Alert,
  Button,
  Snackbar,
} from "@mui/material";
import {
  Search as SearchIcon,
  Edit as EditIcon,
  Clear as ClearIcon,
  Add as AddIcon,
} from "@mui/icons-material";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";
import { Tenant } from "../services/TenantService";
import { useTenants } from "../hooks/useTenants";
import TenantModal from "./TenantModal";
import { TenantModalType } from "../enums/TenantModalType";

const STATUS_COLORS = {
  ACTIVE: "success",
  INACTIVE: "warning",
  DELETED: "error",
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
  } = useTenants();
  const canCreateTenant =
    permissionsLoaded && ability.can("POST", "/m8flow/tenant-realms");
  const { t } = useTranslation();

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
  const [successMessage, setSuccessMessage] = useState("");

  // Handle edit
  const handleEdit = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    setModalType(TenantModalType.EDIT_TENANT);
    setIsModalOpen(true);
  };

  const handleCreate = () => {
    setSelectedTenant(null);
    setModalType(TenantModalType.CREATE_TENANT);
    setIsModalOpen(true);
  };

  // Handle delete
  const handleDeleteClick = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    setModalType(TenantModalType.DELETE_TENANT);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTenant(null);
  };

  const handleModalSuccess = (message: string) => {
    setSuccessMessage(message);
    refetch();
  };

  // Filter and search logic
  const filteredAndSortedTenants = useMemo(() => {
    let filtered = [...tenants];

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
    tenants,
    searchQuery,
    searchType,
    statusFilter,
    sortField,
    sortDirection,
  ]);

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
          <Typography
            variant="h4"
            component="h1"
            style={{ fontWeight: "bold", fontSize: "24px" }}
          >
            {t('tenant_management')}
          </Typography>
          {canCreateTenant && (
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreate}
              data-testid="tenant-add-button"
            >
              {t('add_tenant')}
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
                  <MenuItem value="name">{t('name')}</MenuItem>
                  <MenuItem value="slug">{t('slug')}</MenuItem>
                </Select>
              </FormControl>

              <TextField
                size="small"
                placeholder={t('search_by_placeholder', { type: searchType === 'name' ? t('name').toLowerCase() : t('slug').toLowerCase() })}
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
              {t('showing_tenants_count', { filtered: filteredAndSortedTenants.length, total: tenants.length })}
            </Typography>
          </Stack>
        </Paper>

        {/* Table */}
        <TableContainer component={Paper}>
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
                  ? t('no_tenants_matching_filters')
                  : t('no_tenants_available')}
              </Typography>
            </Box>
          ) : (
            <Table data-testid="tenant-table">
              <TableHead>
                <TableRow>
                  <TableCell>
                    <TableSortLabel
                      active={sortField === "name"}
                      direction={sortField === "name" ? sortDirection : "asc"}
                      onClick={() => handleSort("name")}
                    >
                      {t('name')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>
                    <TableSortLabel
                      active={sortField === "slug"}
                      direction={sortField === "slug" ? sortDirection : "asc"}
                      onClick={() => handleSort("slug")}
                    >
                      {t('slug')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>{t('status')}</TableCell>
                  <TableCell align="center">{t('actions')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredAndSortedTenants.map((tenant) => (
                  <TableRow
                    key={tenant.id}
                    hover
                    data-testid={`tenant-row-${tenant.id}`}
                    sx={{ "&:last-child td, &:last-child th": { border: 0 } }}
                  >
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>
                        {tenant.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {tenant.slug}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={tenant.status}
                        color={STATUS_COLORS[tenant.status]}
                        size="small"
                        sx={{
                          fontWeight: 600,
                          minWidth: 85,
                          fontSize: "0.75rem",
                        }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Stack
                        direction="row"
                        spacing={1}
                        justifyContent="center"
                      >
                        <Tooltip
                          title={t('edit_tenant')}
                          disableHoverListener={tenant.status === "DELETED"}
                        >
                          <span
                            style={{
                              cursor:
                                tenant.status === "DELETED"
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            <IconButton
                              size="small"
                              color="primary"
                              data-testid={`tenant-edit-button-${tenant.id}`}
                              onClick={() => handleEdit(tenant)}
                              disabled={tenant.status === "DELETED"}
                            >
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        {/* TODO: Phase 2 - Delete functionality will be implemented in Phase 2 */}
                        {/* <Tooltip
                          title="Delete Tenant"
                          disableHoverListener={tenant.status === "DELETED"}
                        >
                          <span
                            style={{
                              cursor:
                                tenant.status === "DELETED"
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleDeleteClick(tenant)}
                              disabled={tenant.status === "DELETED"}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip> */}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TableContainer>
      </Stack>

      <TenantModal
        open={isModalOpen}
        type={modalType}
        tenant={selectedTenant}
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
