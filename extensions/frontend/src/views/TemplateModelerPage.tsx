import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Alert,
  Typography,
  Paper,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import ProcessBreadcrumb from '@spiffworkflow-frontend/components/ProcessBreadcrumb';
import DateAndTimeService from '@spiffworkflow-frontend/services/DateAndTimeService';
import HttpService from '../services/HttpService';
import TemplateService from '../services/TemplateService';
import TemplateFileList from '../components/TemplateFileList';
import { Template } from '../types/template';
import { normalizeTemplate } from '../utils/templateHelpers';
import './TemplateModelerPage.css';

function TemplateDetailsCard({
  template,
  onExport,
  onPublish,
}: {
  template: Template;
  onExport: () => void;
  onPublish: () => void;
}) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 1.5,
        mb: 1,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
      }}
    >
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {template.name}
        </Typography>
        <Chip size="small" label={`Version: ${template.version}`} variant="outlined" />
        {template.category && (
          <Chip size="small" label={`Category: ${template.category}`} variant="outlined" />
        )}
        <Chip size="small" label={`Visibility: ${template.visibility}`} variant="outlined" />
        {template.status && (
          <Chip size="small" label={`Status: ${template.status}`} variant="outlined" />
        )}
        {template.createdBy && (
          <Typography variant="caption" color="text.secondary">
            Created by: {template.createdBy}
          </Typography>
        )}
        <Typography variant="caption" color="text.secondary">
          Created: {DateAndTimeService.convertSecondsToFormattedDateTime(template.createdAtInSeconds) ?? '—'}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Updated: {DateAndTimeService.convertSecondsToFormattedDateTime(template.updatedAtInSeconds) ?? '—'}
        </Typography>
        <Button size="small" variant="contained" onClick={onExport} sx={{ ml: 1 }}>
          Export template
        </Button>
        {!template.isPublished && (
          <Button size="small" variant="contained" color="primary" onClick={onPublish}>
            Publish
          </Button>
        )}
      </Box>
      {template.description && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', mt: 0.5, maxWidth: '100%' }}
        >
          {template.description.length > 120
            ? `${template.description.slice(0, 120)}...`
            : template.description}
        </Typography>
      )}
      <TemplateFileList template={template} templateId={template.id} />
    </Paper>
  );
}

export default function TemplateModelerPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishSuccess, setPublishSuccess] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [publishedVersions, setPublishedVersions] = useState<Template[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const id = templateId ? parseInt(templateId, 10) : NaN;

  const handleExport = useCallback(() => {
    if (isNaN(id)) return;
    setExportError(null);
    TemplateService.exportTemplate(id)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `template-${template?.templateKey ?? id}-${template?.version ?? 'export'}.zip`;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch((err) => setExportError(err instanceof Error ? err.message : 'Export failed'));
  }, [id, template?.templateKey, template?.version]);

  useEffect(() => {
    if (!templateId || isNaN(id)) {
      setError('Invalid template ID');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    HttpService.makeCallToBackend({
      path: `/v1.0/m8flow/templates/${id}`,
      httpMethod: HttpService.HttpMethods.GET,
      successCallback: (result: Record<string, unknown>) => {
        setTemplate(normalizeTemplate(result));
        setLoading(false);
      },
      failureCallback: (err: any) => {
        setError(err?.message ?? 'Failed to load template');
        setLoading(false);
      },
    });
  }, [templateId, id]);

  useEffect(() => {
    if (!template?.templateKey) {
      setPublishedVersions([]);
      return;
    }
    setVersionsLoading(true);
    TemplateService.getPublishedVersions(template.templateKey)
      .then(setPublishedVersions)
      .catch(() => setPublishedVersions([]))
      .finally(() => setVersionsLoading(false));
  }, [template?.templateKey]);

  const handlePublish = useCallback(() => {
    if (!template || isNaN(id)) return;
    setPublishSuccess(false);
    setError(null);
    HttpService.makeCallToBackend({
      path: `/v1.0/m8flow/templates/${id}`,
      httpMethod: HttpService.HttpMethods.PUT,
      postBody: { is_published: true },
      successCallback: (result: Record<string, unknown>) => {
        setTemplate(normalizeTemplate(result));
        setPublishSuccess(true);
      },
      failureCallback: (err: any) => {
        setError(err?.message ?? 'Failed to publish template');
      },
    });
  }, [id, template]);

  const SUCCESS_ALERT_DURATION_MS = 5000;
  useEffect(() => {
    if (!publishSuccess) return;
    const timer = window.setTimeout(() => setPublishSuccess(false), SUCCESS_ALERT_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [publishSuccess]);

  if (loading && !template) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !template) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
        <Button onClick={() => navigate('/templates')} sx={{ mt: 2 }}>
          Back to Templates
        </Button>
      </Box>
    );
  }

  if (!template) {
    return null;
  }

  const hotCrumbs: [string, string?][] = [
    ['Templates', '/templates'],
    [template.name],
  ];

  return (
    <Box sx={{ px: 2, pl: 3, pb: 3 }}>
      <Box sx={{ mb: 1 }}>
        <ProcessBreadcrumb hotCrumbs={hotCrumbs} />
      </Box>
      <Typography variant="h5" component="h1" sx={{ mb: 1 }}>
        Template: {template.name}
      </Typography>
      {publishedVersions.length > 0 && (
        <Paper
          elevation={0}
          sx={{
            p: 1.5,
            mb: 1,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
          }}
        >
          <FormControl size="small" sx={{ minWidth: 220 }} disabled={versionsLoading}>
            <InputLabel id="template-version-label">Published versions</InputLabel>
            <Select
              labelId="template-version-label"
              label="Published versions"
              value={template.id}
              onChange={(e) => {
                const selectedId = Number(e.target.value);
                if (selectedId !== template.id) navigate(`/templates/${selectedId}`);
              }}
            >
              {publishedVersions.map((v) => (
                <MenuItem key={v.id} value={v.id}>
                  {v.version}
                  {v.id === template.id ? ' (current)' : ''}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Paper>
      )}
      <TemplateDetailsCard template={template} onExport={handleExport} onPublish={handlePublish} />
      {exportError && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setExportError(null)}>
          {exportError}
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {publishSuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setPublishSuccess(false)}>
          Template published successfully.
        </Alert>
      )}
    </Box>
  );
}
