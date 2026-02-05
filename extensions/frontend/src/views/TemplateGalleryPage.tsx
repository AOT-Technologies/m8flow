import { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Grid,
  CircularProgress,
  Alert,
  Paper,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useTemplates } from '../hooks/useTemplates';
import { TemplateFilters as TemplateFiltersType, Template } from '../types/template';
import TemplateCard from '../components/TemplateCard';
import TemplateFilters from '../components/TemplateFilters';

export default function TemplateGalleryPage() {
  const navigate = useNavigate();
  const { templates, templatesLoading, error, fetchTemplates } = useTemplates();
  const [filters, setFilters] = useState<TemplateFiltersType>({
    latest_only: true,
  });

  // Fetch templates on mount and when filters change
  useEffect(() => {
    fetchTemplates(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

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
    setFilters(newFilters);
  };

  const handleUseTemplate = (template: Template) => {
    // Navigate to template detail or start process
    console.log('Use template:', template);
  };

  const handleViewTemplate = (template: Template) => {
    navigate(`/templates/${template.id}`);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 3 }}>
        Template Gallery
      </Typography>

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
          ) : (
            <Grid container spacing={2}>
              {galleryTemplates.map((template) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={template.id}>
                  <TemplateCard
                    template={template}
                    onUseTemplate={() => handleUseTemplate(template)}
                    onViewTemplate={() => handleViewTemplate(template)}
                  />
                </Grid>
              ))}
            </Grid>
          )}
        </>
      )}
    </Box>
  );
}
