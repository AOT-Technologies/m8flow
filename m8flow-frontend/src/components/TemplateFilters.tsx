import {
  Box,
  InputAdornment,
  Paper,
  TextField,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Chip,
  Stack,
} from '@mui/material';
import { useState, useEffect, useRef } from 'react';
import { useDebouncedCallback } from 'use-debounce';
import { useTranslation } from 'react-i18next';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import { TemplateFilters as TemplateFiltersType, TemplateVisibility } from '../types/template';

interface TemplateFiltersProps {
  filters: TemplateFiltersType;
  onFiltersChange: (filters: TemplateFiltersType) => void;
  availableCategories?: string[];
  availableTags?: string[];
}

export default function TemplateFilters({
  filters,
  onFiltersChange,
  availableCategories = [],
  availableTags = [],
}: TemplateFiltersProps) {
  const { t } = useTranslation();
  const [searchText, setSearchText] = useState(filters.search || '');
  const isInitialMount = useRef(true);
  const filtersRef = useRef(filters);
  const onFiltersChangeRef = useRef(onFiltersChange);

  // Keep refs in sync with latest values
  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    onFiltersChangeRef.current = onFiltersChange;
  }, [onFiltersChange]);

  // Sync searchText with filters.search when filters change externally
  useEffect(() => {
    if (filters.search !== searchText) {
      setSearchText(filters.search || '');
    }
  }, [filters.search]);

  // Debounce search input - use refs to avoid stale closure
  const debouncedSearch = useDebouncedCallback((value: string) => {
    onFiltersChangeRef.current({ ...filtersRef.current, search: value || undefined });
  }, 300);

  useEffect(() => {
    // Skip on initial mount to prevent infinite loop
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    debouncedSearch(searchText);
  }, [searchText, debouncedSearch]);

  const handleCategoryChange = (category: string) => {
    onFiltersChange({
      ...filters,
      category: category || undefined,
    });
  };

  const handleVisibilityChange = (visibility: TemplateVisibility | '') => {
    onFiltersChange({
      ...filters,
      visibility: visibility || undefined,
    });
  };

  const handleTagChange = (tag: string) => {
    onFiltersChange({
      ...filters,
      tag: tag || undefined,
    });
  };

  const handleOwnerChange = (owner: string) => {
    onFiltersChange({
      ...filters,
      owner: owner || undefined,
    });
  };

  return (
    <Paper
      elevation={0}
      sx={{
        width: '100%',
        display: 'flex',
        gap: 2,
        flexWrap: 'wrap',
        padding: 2,
        borderColor: 'borders.primary',
        borderWidth: 1,
        borderStyle: 'solid',
        mb: 2,
      }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 200 }}>
        <TextField
          size="small"
          fullWidth
          variant="outlined"
          placeholder={t("search_templates")}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          data-testid="template-filters-search-input"
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <SearchOutlinedIcon />
              </InputAdornment>
            ),
          }}
        />
      </Box>

      <FormControl size="small" sx={{ minWidth: 150 }}>
        <InputLabel>{t("category")}</InputLabel>
        <Select
          value={filters.category || ''}
          label={t("category")}
          data-testid="template-filters-category-select"
          onChange={(e) => handleCategoryChange(e.target.value)}
        >
          <MenuItem value="">
            <em>{t("all_categories")}</em>
          </MenuItem>
          {availableCategories.map((category) => (
            <MenuItem key={category} value={category}>
              {category}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 150 }}>
        <InputLabel>{t("visibility")}</InputLabel>
        <Select
          value={filters.visibility || ''}
          label={t("visibility")}
          data-testid="template-filters-visibility-select"
          onChange={(e) => handleVisibilityChange(e.target.value as TemplateVisibility | '')}
        >
          <MenuItem value="">
            <em>{t("all")}</em>
          </MenuItem>
          <MenuItem value="PUBLIC">{t("public")}</MenuItem>
          <MenuItem value="TENANT">{t("tenant")}</MenuItem>
          <MenuItem value="PRIVATE">{t("private")}</MenuItem>
        </Select>
      </FormControl>

      {availableTags.length > 0 && (
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>{t("tag")}</InputLabel>
          <Select
            value={filters.tag || ''}
            label={t("tag")}
            data-testid="template-filters-tag-select"
            onChange={(e) => handleTagChange(e.target.value)}
          >
            <MenuItem value="">
              <em>{t("all_tags")}</em>
            </MenuItem>
            {availableTags.map((tag) => (
              <MenuItem key={tag} value={tag}>
                {tag}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {filters.search && (
        <Chip
          label={`Search: ${filters.search}`}
          onDelete={() => {
            setSearchText('');
            onFiltersChange({ ...filters, search: undefined });
          }}
          size="small"
        />
      )}
      {filters.category && (
        <Chip
          label={`Category: ${filters.category}`}
          onDelete={() => handleCategoryChange('')}
          size="small"
        />
      )}
      {filters.visibility && (
        <Chip
          label={`Visibility: ${filters.visibility}`}
          onDelete={() => handleVisibilityChange('')}
          size="small"
        />
      )}
      {filters.tag && (
        <Chip
          label={`Tag: ${filters.tag}`}
          onDelete={() => handleTagChange('')}
          size="small"
        />
      )}
    </Paper>
  );
}
