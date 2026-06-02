import { useState, useEffect, useMemo, MouseEvent } from 'react';
import {
  Box,
  Typography,
  Grid,
  CircularProgress,
  Alert,
  Paper,
  Button,
  ToggleButtonGroup,
  ToggleButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Chip,
  Tooltip,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  ViewModule,
  ViewList,
  Visibility,
  MoreVert,
  Edit,
  FileDownload,
  Delete,
  Restore,
} from '@mui/icons-material';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { useTemplates } from '../hooks/useTemplates';
import { TemplateFilters as TemplateFiltersType, Template } from '../types/template';
import TemplateCard from '../components/TemplateCard';
import TemplateFilters from '../components/TemplateFilters';
import ImportTemplateModal from '../components/ImportTemplateModal';
import TemplateDeleteConfirmDialog, { TemplateRestoreConfirmDialog } from '../components/TemplateDeleteConfirmDialog';
import PaginationForTable from '@spiffworkflow-frontend/components/PaginationForTable';
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";
import { useTranslation } from 'react-i18next';
import TemplateService from '../services/TemplateService';
import UserService from '../services/UserService';

const DEFAULT_PER_PAGE = 10;

export default function TemplateGalleryPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { templates, pagination, templatesLoading, error, fetchTemplates } = useTemplates();
  const [filters, setFilters] = useState<TemplateFiltersType>({
    latest_only: true,
    include_deleted: false,
    deleted_only: false,
  });
  const [importOpen, setImportOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card');
  const [templateMode, setTemplateMode] = useState<'active' | 'deleted'>('active');
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const { ability, permissionsLoaded } = usePermissionFetcher({
    "/m8flow/templates": ["POST", "PUT", "DELETE"],
    "/m8flow/admin/templates": ["DELETE"],
  });
  const { t } = useTranslation();
  const isSuperAdmin = UserService.isSuperAdmin();

  const canCreate = ability.can("POST", "/m8flow/templates");
  const canEdit = ability.can("PUT", "/m8flow/templates");
  const canDelete = ability.can("DELETE", "/m8flow/templates");
  // RBAC: admin-level template permission (delete published, restore)
  const hasAdminPermission = permissionsLoaded && ability.can("DELETE", "/m8flow/admin/templates");
  const currentUsername = UserService.getUserName() || UserService.getPreferredUsername() || "";

  // Delete confirmation dialog state
  const [deleteTarget, setDeleteTarget] = useState<Template | null>(null);
  // Restore confirmation dialog state
  const [restoreTarget, setRestoreTarget] = useState<Template | null>(null);

  // Table row overflow menu state
  const [rowMenuAnchor, setRowMenuAnchor] = useState<null | HTMLElement>(null);
  const [rowMenuTemplate, setRowMenuTemplate] = useState<Template | null>(null);

  // Read page/per_page from URL search params (PaginationForTable manages them)
  const page = Number.parseInt(searchParams.get('page') || '1', 10) || 1;
  const perPage = Number.parseInt(searchParams.get('per_page') || String(DEFAULT_PER_PAGE), 10) || DEFAULT_PER_PAGE;

  // Fetch templates on mount and when filters or pagination change
  useEffect(() => {
    fetchTemplates({ ...filters, page, per_page: perPage });
  }, [filters, page, perPage, fetchTemplates]);



  // Extract unique categories and tags from templates for filter options
  const { availableCategories, availableTags } = useMemo(() => {
    const categories = new Set<string>();
    const tags = new Set<string>();

    templates.forEach((template) => {
      if (template.category) {
        categories.add(template.category);
      }
      if (template.tags) {
        template.tags.forEach((tag) => tags.add(tag));
      }
    });

    return {
      availableCategories: Array.from(categories).sort(),
      availableTags: Array.from(tags).sort(),
    };
  }, [templates]);

  // Show all templates in main gallery (no tag-based filtering)
  const galleryTemplates = useMemo(() => {
    return templates;
  }, [templates]);
  const hasActiveFilters = Boolean(filters.search || filters.category || filters.visibility || filters.tag || filters.owner);

  const handleFiltersChange = (newFilters: TemplateFiltersType) => {
    // Reset to page 1 when filters change
    const params = new URLSearchParams(searchParams);
    params.set('page', '1');
    navigate({ search: params.toString() }, { replace: true });
    setFilters(newFilters);
  };

  const handleUseTemplate = (template: Template) => {
    navigate(`/templates/${template.id}`);
  };

  const handleViewTemplate = (template: Template) => {
    navigate(`/templates/${template.id}`);
  };

  const handleImportSuccess = (template: Template) => {
    fetchTemplates({ ...filters, page, per_page: perPage });
    navigate(`/templates/${template.id}`);
  };

  const refreshTemplates = () => {
    fetchTemplates({ ...filters, page, per_page: perPage });
  };

  const handleTemplateModeChange = (_: unknown, value: 'active' | 'deleted' | null) => {
    if (!value) return;
    setTemplateMode(value);
    const params = new URLSearchParams(searchParams);
    params.set('page', '1');
    navigate({ search: params.toString() }, { replace: true });
    setFilters((prev) => ({
      ...prev,
      latest_only: value === 'active',
      include_deleted: value === 'deleted',
      deleted_only: value === 'deleted',
    }));
  };

  const canDeleteTemplate = (template: Template): boolean => {
    if (!canDelete) return false;
    if (template.isPublished) return hasAdminPermission;
    return hasAdminPermission || (!!currentUsername && template.createdBy === currentUsername);
  };

  const deleteDisabledReason = (template: Template): string => {
    if (template.isPublished && !hasAdminPermission) {
      return t("published_delete_admin_only", {
        defaultValue: "Insufficient permissions to delete published templates.",
      });
    }
    if (!hasAdminPermission && currentUsername !== template.createdBy) {
      return t("draft_delete_owner_or_admin_only", {
        defaultValue: "Only the template creator or an admin can delete this draft template.",
      });
    }
    return "";
  };

  const canRestoreTemplate = canDelete && hasAdminPermission;

  // Open delete confirmation dialog instead of window.confirm
  const handleDeleteTemplate = (template: Template) => {
    setDeleteTarget(template);
  };

  // Actually perform the delete after user confirms via dialog
  const confirmDeleteTemplate = () => {
    if (!deleteTarget) return;
    const template = deleteTarget;
    setDeleteTarget(null);
    TemplateService.deleteTemplate(template.id)
      .then(() => {
        setActionMessage({
          type: 'success',
          text: t("template_deleted_successfully", { defaultValue: "Template deleted successfully." }),
        });
        refreshTemplates();
      })
      .catch((err) => {
        setActionMessage({
          type: 'error',
          text: err instanceof Error ? err.message : t("delete_failed", { defaultValue: "Delete failed" }),
        });
      });
  };

  // Open restore confirmation dialog instead of window.confirm
  const handleRestoreTemplate = (template: Template) => {
    setRestoreTarget(template);
  };

  // Actually perform the restore after user confirms via dialog
  const confirmRestoreTemplate = () => {
    if (!restoreTarget) return;
    const template = restoreTarget;
    setRestoreTarget(null);
    TemplateService.restoreTemplate(template.id)
      .then(() => {
        setActionMessage({
          type: 'success',
          text: t("template_restored_successfully", { defaultValue: "Template restored successfully." }),
        });
        refreshTemplates();
      })
      .catch((err) => {
        setActionMessage({
          type: 'error',
          text: err instanceof Error ? err.message : t("restore_failed", { defaultValue: "Restore failed" }),
        });
      });
  };

  const handleEditTemplate = (template: Template) => {
    navigate(`/templates/${template.id}`);
  };

  const handleExportTemplate = (template: Template) => {
    TemplateService.exportTemplate(template.id)
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${template.templateKey || template.name}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      })
      .catch((err) => {
        setActionMessage({
          type: 'error',
          text: err instanceof Error ? err.message : t("export_failed", { defaultValue: "Export failed" }),
        });
      });
  };

  // Table row overflow menu handlers
  const handleRowMenuOpen = (event: MouseEvent<HTMLElement>, template: Template) => {
    event.stopPropagation();
    setRowMenuAnchor(event.currentTarget);
    setRowMenuTemplate(template);
  };

  const handleRowMenuClose = () => {
    setRowMenuAnchor(null);
    setRowMenuTemplate(null);
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            {t("template_gallery")}
          </Typography>
          {isSuperAdmin && (
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label="Super Admin View"
              data-testid="template-gallery-super-admin-view"
            />
          )}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ToggleButtonGroup
            value={templateMode}
            exclusive
            onChange={handleTemplateModeChange}
            size="small"
            aria-label={t("template_mode", { defaultValue: "Template mode" })}
            data-testid="template-gallery-mode-toggle"
          >
            <ToggleButton value="active" data-testid="template-gallery-mode-active">
              {t("active_templates", { defaultValue: "Active" })}
            </ToggleButton>
            <ToggleButton value="deleted" data-testid="template-gallery-mode-deleted">
              {t("deleted_templates", { defaultValue: "Deleted" })}
            </ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, value) => value != null && setViewMode(value)}
            size="small"
            aria-label={t("view_mode")}
            data-testid="template-gallery-view-mode-toggle"
          >
            <ToggleButton value="card" aria-label={t("card_view")} data-testid="template-gallery-view-card">
              <ViewModule />
            </ToggleButton>
            <ToggleButton value="table" aria-label={t("table_view")} data-testid="template-gallery-view-table">
              <ViewList />
            </ToggleButton>
          </ToggleButtonGroup>
          {canCreate && (
            <Button variant="outlined" onClick={() => setImportOpen(true)} data-testid="template-gallery-import-button">
              {t("import_template_zip")}
            </Button>
          )}
        </Box>
      </Box>
      {canCreate && (
        <ImportTemplateModal
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onSuccess={handleImportSuccess}
        />
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {actionMessage && (
        <Alert
          severity={actionMessage.type}
          sx={{ mb: 2 }}
          onClose={() => setActionMessage(null)}
        >
          {actionMessage.text}
        </Alert>
      )}

      {templatesLoading && templates.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {/* Filters */}
          <TemplateFilters
            filters={filters}
            onFiltersChange={handleFiltersChange}
            availableCategories={availableCategories}
            availableTags={availableTags}
            showTenantFilter={isSuperAdmin}
          />

          {/* Main Gallery */}
          {templatesLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : galleryTemplates.length === 0 ? (
            <Paper
              elevation={0}
              sx={{
                p: 4,
                textAlign: 'center',
                border: '1px solid',
                borderColor: 'borders.primary',
                borderRadius: 2,
              }}
            >
              <Typography variant="h6" sx={{ mb: 1 }}>
                {t("no_templates_found")}
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {hasActiveFilters
                  ? t("try_adjusting_filters_templates")
                  : t("no_templates_available")}
              </Typography>
            </Paper>
          ) : viewMode === 'table' ? (
            <PaginationForTable
              page={page}
              perPage={perPage}
              perPageOptions={[10, 25, 50, 100]}
              pagination={pagination}
              paginationDataTestidTag="template-gallery-pagination"
              tableToDisplay={
                <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid', borderColor: 'borders.primary', borderRadius: 2 }}>
                    <Table size="medium" sx={{ minWidth: 650, '& td': { wordBreak: 'break-word' } }} data-testid="template-gallery-table">
                    <TableHead>
                      <TableRow>
                        <TableCell>{t("name")}</TableCell>
                        <TableCell>{t("key")}</TableCell>
                        <TableCell>{t("version")}</TableCell>
                        {isSuperAdmin && <TableCell>{t("tenant")}</TableCell>}
                        {isSuperAdmin && <TableCell>Owner</TableCell>}
                        <TableCell>{t("category")}</TableCell>
                        <TableCell>{t("updated")}</TableCell>
                        <TableCell align="right">{t("actions")}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {galleryTemplates.map((template) => (
                        <TableRow
                          key={template.id}
                          hover
                          sx={{ cursor: 'pointer' }}
                          onClick={() => handleViewTemplate(template)}
                          data-testid={`template-gallery-row-${template.id}`}
                        >
                          <TableCell>
                            <Link
                              to={`/templates/${template.id}`}
                              onClick={(e) => e.stopPropagation()}
                              style={{ fontWeight: 600, textDecoration: 'none' }}
                            >
                              {template.name}
                            </Link>
                          </TableCell>
                          <TableCell>{template.templateKey}</TableCell>
                          <TableCell>{template.version}</TableCell>
                          {isSuperAdmin && (
                            <TableCell>
                              {template.tenant?.name || template.tenant?.slug || template.tenantId || '--'}
                            </TableCell>
                          )}
                          {isSuperAdmin && <TableCell>{template.createdBy || '--'}</TableCell>}
                          <TableCell>{template.category || '--'}</TableCell>
                          <TableCell>
                            <Typography variant="caption" title={new Date(template.updatedAtInSeconds * 1000).toISOString()}>
                              {formatDistanceToNow(new Date(template.updatedAtInSeconds * 1000), { addSuffix: true })}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <IconButton
                              component={Link}
                              to={`/templates/${template.id}`}
                              size="small"
                              aria-label={t("view_template", { defaultValue: "View template" })}
                              data-testid={`template-gallery-view-button-${template.id}`}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Visibility />
                            </IconButton>
                            <IconButton
                              size="small"
                              aria-label={t("more_actions", { defaultValue: "More actions" })}
                              data-testid={`template-gallery-more-actions-${template.id}`}
                              onClick={(e) => handleRowMenuOpen(e, template)}
                            >
                              <MoreVert />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              }
            />
          ) : (
            <PaginationForTable
              page={page}
              perPage={perPage}
              perPageOptions={[10, 25, 50, 100]}
              pagination={pagination}
              paginationDataTestidTag="template-gallery-pagination"
              tableToDisplay={
                <Grid container spacing={2}>
                  {galleryTemplates.map((template) => (
                    <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }} key={template.id}>
                      <TemplateCard
                        template={template}
                        onUseTemplate={() => handleUseTemplate(template)}
                        onViewTemplate={() => handleViewTemplate(template)}
                        showTenantContext={isSuperAdmin}
                        onEditTemplate={templateMode === 'active' && canEdit ? () => handleEditTemplate(template) : undefined}
                        onExportTemplate={templateMode === 'active' ? () => handleExportTemplate(template) : undefined}
                        onDeleteTemplate={templateMode === 'active' && canDelete ? () => handleDeleteTemplate(template) : undefined}
                        onRestoreTemplate={templateMode === 'deleted' ? () => handleRestoreTemplate(template) : undefined}
                        deleteDisabled={templateMode === 'active' ? !canDeleteTemplate(template) : false}
                        deleteDisabledReason={deleteDisabledReason(template)}
                        restoreDisabled={templateMode === 'deleted' ? !canRestoreTemplate : false}
                        restoreDisabledReason={t("restore_admin_only", {
                          defaultValue: "Insufficient permissions to restore deleted templates.",
                        })}
                      />
                    </Grid>
                  ))}
                </Grid>
              }
            />
          )}
        </>
      )}

      {/* Shared table-row overflow menu (rendered once, positioned via anchorEl) */}
      <Menu
        anchorEl={rowMenuAnchor}
        open={Boolean(rowMenuAnchor)}
        onClose={handleRowMenuClose}
        onClick={(e) => e.stopPropagation()}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        data-testid="template-gallery-row-actions-menu"
      >
        {templateMode === 'active' && (
          <>
            {canEdit && (
              <MenuItem
                onClick={() => {
                  if (rowMenuTemplate) handleEditTemplate(rowMenuTemplate);
                  handleRowMenuClose();
                }}
                data-testid="template-row-edit-action"
              >
                <ListItemIcon>
                  <Edit fontSize="small" />
                </ListItemIcon>
                <ListItemText>{t("edit", { defaultValue: "Edit" })}</ListItemText>
              </MenuItem>
            )}
            <MenuItem
              onClick={() => {
                if (rowMenuTemplate) handleExportTemplate(rowMenuTemplate);
                handleRowMenuClose();
              }}
              data-testid="template-row-export-action"
            >
              <ListItemIcon>
                <FileDownload fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t("export", { defaultValue: "Export" })}</ListItemText>
            </MenuItem>
          </>
        )}
        {templateMode === 'deleted' ? (
          <Tooltip
            title={
              canRestoreTemplate
                ? ""
                : t("restore_admin_only", {
                    defaultValue: "Insufficient permissions to restore deleted templates.",
                  })
            }
          >
            <span>
              <MenuItem
                onClick={() => {
                  if (rowMenuTemplate && canRestoreTemplate) handleRestoreTemplate(rowMenuTemplate);
                  handleRowMenuClose();
                }}
                disabled={!canRestoreTemplate}
                data-testid="template-row-restore-action"
              >
                <ListItemIcon>
                  <Restore fontSize="small" />
                </ListItemIcon>
                <ListItemText>{t("restore", { defaultValue: "Restore" })}</ListItemText>
              </MenuItem>
            </span>
          </Tooltip>
        ) : canDelete ? (
          <Tooltip
            title={
              rowMenuTemplate && !canDeleteTemplate(rowMenuTemplate)
                ? deleteDisabledReason(rowMenuTemplate)
                : ""
            }
          >
            <span>
              <MenuItem
                onClick={() => {
                  if (rowMenuTemplate && canDeleteTemplate(rowMenuTemplate)) handleDeleteTemplate(rowMenuTemplate);
                  handleRowMenuClose();
                }}
                disabled={rowMenuTemplate ? !canDeleteTemplate(rowMenuTemplate) : true}
                data-testid="template-row-delete-action"
                sx={{ color: 'error.main' }}
              >
                <ListItemIcon>
                  <Delete fontSize="small" color="error" />
                </ListItemIcon>
                <ListItemText>{t("delete")}</ListItemText>
              </MenuItem>
            </span>
          </Tooltip>
        ) : null}
      </Menu>

      {/* Delete confirmation dialog */}
      <TemplateDeleteConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDeleteTemplate}
        templateName={deleteTarget?.name || ""}
        isPublished={deleteTarget?.isPublished || false}
      />

      {/* Restore confirmation dialog */}
      <TemplateRestoreConfirmDialog
        open={Boolean(restoreTarget)}
        onClose={() => setRestoreTarget(null)}
        onConfirm={confirmRestoreTemplate}
        templateName={restoreTarget?.name || ""}
      />
    </Box>
  );
}
