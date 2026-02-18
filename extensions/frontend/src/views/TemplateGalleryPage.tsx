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
} from '@mui/material';
import { ViewModule, ViewList, Visibility } from '@mui/icons-material';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { useTemplates } from '../hooks/useTemplates';
import { TemplateFilters as TemplateFiltersType, Template } from '../types/template';
import TemplateCard from '../components/TemplateCard';
import TemplateFilters from '../components/TemplateFilters';
import ImportTemplateModal from '../components/ImportTemplateModal';
import PaginationForTable from '@spiffworkflow-frontend/components/PaginationForTable';

const DEFAULT_PER_PAGE = 10;

export default function TemplateGalleryPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { templates, pagination, templatesLoading, error, fetchTemplates } = useTemplates();
  const [filters, setFilters] = useState<TemplateFiltersType>({
    latest_only: true,
  });
  const [importOpen, setImportOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card');

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
    fetchTemplates(filters);
    navigate(`/templates/${template.id}`);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700 }}>
          Template Gallery
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, value) => value != null && setViewMode(value)}
            size="small"
            aria-label="View mode"
          >
            <ToggleButton value="card" aria-label="Card view">
              <ViewModule />
            </ToggleButton>
            <ToggleButton value="table" aria-label="Table view">
              <ViewList />
            </ToggleButton>
          </ToggleButtonGroup>
          <Button variant="outlined" onClick={() => setImportOpen(true)}>
            Import template (zip)
          </Button>
        </Box>
      </Box>
      <ImportTemplateModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={handleImportSuccess}
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
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
                No templates found
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {Object.keys(filters).length > 1
                  ? 'Try adjusting your filters to see more templates.'
                  : 'No templates are available at this time.'}
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
                  <Table size="medium" className="process-model-file-table">
                    <TableHead>
                      <TableRow>
                        <TableCell>Name</TableCell>
                        <TableCell>Key</TableCell>
                        <TableCell>Version</TableCell>
                        <TableCell>Category</TableCell>
                        <TableCell>Updated</TableCell>
                        <TableCell align="right">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {galleryTemplates.map((template) => (
                        <TableRow
                          key={template.id}
                          hover
                          sx={{ cursor: 'pointer' }}
                          onClick={() => handleViewTemplate(template)}
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
                              aria-label="View template"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Visibility />
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
