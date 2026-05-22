import { useState, useEffect, useMemo } from 'react';
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
  Tooltip,
} from '@mui/material';
import { ViewModule, ViewList, Visibility, Delete, Restore } from '@mui/icons-material';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { useTemplates } from '../hooks/useTemplates';
import { TemplateFilters as TemplateFiltersType, Template } from '../types/template';
import TemplateCard from '../components/TemplateCard';
import TemplateFilters from '../components/TemplateFilters';
import ImportTemplateModal from '../components/ImportTemplateModal';
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
    "/m8flow/templates": ["POST", "DELETE"],
    "/m8flow/admin/templates": ["DELETE"],
  });
  const { t } = useTranslation();

  const canCreate = ability.can("POST", "/m8flow/templates");
  const canDelete = ability.can("DELETE", "/m8flow/templates");
  // RBAC: admin-level template permission (delete published, restore)
  const hasAdminPermission = permissionsLoaded && ability.can("DELETE", "/m8flow/admin/templates");
  const currentUsername = UserService.getUserName() || UserService.getPreferredUsername() || "";

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

  const handleDeleteTemplate = (template: Template) => {
    const confirmMessage = template.isPublished
      ? t("delete_template_published_confirm", {
          name: template.name,
          defaultValue: `Delete published template "${template.name}"? It will be soft-deleted and can be restored later.`,
        })
      : t("delete_template_draft_confirm", {
          name: template.name,
          defaultValue: `Delete draft template "${template.name}"? This will permanently remove it.`,
        });
    if (!globalThis.confirm(confirmMessage)) return;
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

  const handleRestoreTemplate = (template: Template) => {
    const confirmMessage = t("restore_template_confirm", {
      name: template.name,
      defaultValue: `Restore template "${template.name}"?`,
    });
    if (!globalThis.confirm(confirmMessage)) return;
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
        <Typography variant="h4" sx={{ fontWeight: 700 }}>
          {t("template_gallery")}
        </Typography>
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
                          <TableCell>{template.category || '—'}</TableCell>
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
                                  <IconButton
                                    size="small"
                                    aria-label={t("restore", { defaultValue: "Restore" })}
                                    data-testid={`template-gallery-restore-button-${template.id}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (!canRestoreTemplate) return;
                                      handleRestoreTemplate(template);
                                    }}
                                    disabled={!canRestoreTemplate}
                                  >
                                    <Restore />
                                  </IconButton>
                                </span>
                              </Tooltip>
                            ) : canDelete ? (
                              <Tooltip title={canDeleteTemplate(template) ? "" : deleteDisabledReason(template)}>
                                <span>
                                  <IconButton
                                    size="small"
                                    aria-label={t("delete", { defaultValue: "Delete" })}
                                    data-testid={`template-gallery-delete-button-${template.id}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (!canDeleteTemplate(template)) return;
                                      handleDeleteTemplate(template);
                                    }}
                                    disabled={!canDeleteTemplate(template)}
                                  >
                                    <Delete />
                                  </IconButton>
                                </span>
                              </Tooltip>
                            ) : null}
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
    </Box>
  );
}
