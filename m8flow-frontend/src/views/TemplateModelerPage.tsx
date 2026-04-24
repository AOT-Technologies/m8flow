import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
import type { SelectChangeEvent } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ProcessBreadcrumb from '@spiffworkflow-frontend/components/ProcessBreadcrumb';
import DateAndTimeService from '@spiffworkflow-frontend/services/DateAndTimeService';
import HttpService from '../services/HttpService';
import TemplateService from '../services/TemplateService';
import TemplateFileList from '../components/TemplateFileList';
import CreateProcessModelFromTemplateModal from '../components/CreateProcessModelFromTemplateModal';
import { Template, TemplateVisibility } from '../types/template';
import { normalizeTemplate } from '../utils/templateHelpers';
import './TemplateModelerPage.css';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';

const VISIBILITY_OPTIONS: { value: TemplateVisibility; label: string }[] = [
  { value: 'PRIVATE', label: 'private_only_you' },
  { value: 'TENANT', label: 'tenant_wide' },
  { value: 'PUBLIC', label: 'public_authenticated_users' },
];

function TemplateDetailsCard({
  template,
  onExport,
  onPublish,
  onCreateProcessModel,
  pendingVisibility,
  onVisibilityChange,
  onSaveVisibility,
  isSaving,
}: {
  template: Template;
  onExport: () => void;
  onPublish: () => void;
  onCreateProcessModel: () => void;
  pendingVisibility: TemplateVisibility | null;
  onVisibilityChange: (visibility: TemplateVisibility) => void;
  onSaveVisibility: () => void;
  isSaving: boolean;
}) {
  const { ability, permissionsLoaded } = usePermissionFetcher({
    "/m8flow/templates": ["POST", "PUT"],
  });

  const canCreate = ability.can("POST", "/m8flow/templates");
  const canPublish = ability.can("PUT", "/m8flow/templates");
  const { t } = useTranslation();

  if (!permissionsLoaded) return null;

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
        <Chip size="small" label={`${t('version')}: ${template.version}`} variant="outlined" />
        {template.category && (
          <Chip size="small" label={`${t('category')}: ${template.category}`} variant="outlined" />
        )}
        {canPublish && !template.isPublished ? (
          <>
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <Select
                data-testid="template-visibility-select"
                value={pendingVisibility ?? template.visibility}
                onChange={(e: SelectChangeEvent) =>
                  onVisibilityChange(e.target.value as TemplateVisibility)
                }
                variant="outlined"
                sx={{ height: 24, fontSize: '0.8125rem' }}
              >
                {VISIBILITY_OPTIONS.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {t(opt.label)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {pendingVisibility && pendingVisibility !== template.visibility && (
              <Button
                size="small"
                variant="contained"
                color="primary"
                data-testid="template-save-visibility-button"
                onClick={onSaveVisibility}
                disabled={isSaving}
              >
                {isSaving ? t('saving') : t('save')}
              </Button>
            )}
          </>
        ) : (
          <Chip size="small" label={`${t('visibility')}: ${template.visibility}`} variant="outlined" />
        )}
        {template.status && (
          <Chip size="small" label={`${t('status')}: ${template.status}`} variant="outlined" />
        )}
        {template.createdBy && (
          <Typography variant="caption" color="text.secondary">
            {t('created_by')}: {template.createdBy}
          </Typography>
        )}
        <Typography variant="caption" color="text.secondary">
          {t('created')}: {DateAndTimeService.convertSecondsToFormattedDateTime(template.createdAtInSeconds) ?? '—'}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {t('updated')}: {DateAndTimeService.convertSecondsToFormattedDateTime(template.updatedAtInSeconds) ?? '—'}
        </Typography>
        {canCreate && (
          <Button
            size="small"
            variant="contained"
            color="success"
            startIcon={<AddIcon />}
            data-testid="template-create-process-model-button"
            onClick={onCreateProcessModel}
          >
            {t('create_process_model')}
          </Button>
        )}
        <Button size="small" variant="contained" data-testid="template-export-button" onClick={onExport}>
          {t('export_template')}
        </Button>
        {canPublish && !template.isPublished && (
          <Button
            size="small"
            variant="contained"
            color="primary"
            data-testid="template-publish-button"
            onClick={onPublish}
          >
            {t('publish')}
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
  const { t } = useTranslation();
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishSuccess, setPublishSuccess] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [allVersions, setAllVersions] = useState<Template[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [createProcessModelOpen, setCreateProcessModelOpen] = useState(false);
  const [createProcessModelSuccess, setCreateProcessModelSuccess] = useState<string | null>(null);
  const [pendingVisibility, setPendingVisibility] = useState<TemplateVisibility | null>(null);
  const [isSavingVisibility, setIsSavingVisibility] = useState(false);
  const [saveVisibilitySuccess, setSaveVisibilitySuccess] = useState(false);

  const id = templateId ? Number.parseInt(templateId, 10) : NaN;

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

  // Fetch all versions when template key changes
  const fetchAllVersions = useCallback(() => {
    if (!template?.templateKey) {
      setAllVersions([]);
      return;
    }
    setVersionsLoading(true);
    TemplateService.getAllVersions(template.templateKey)
      .then((versions) => {
        // Sort versions: V1, V2, V3... (ascending by version number)
        const sorted = [...versions].sort((a, b) => {
          const aNum = Number.parseInt(a.version.replace(/^V/i, ''), 10) || 0;
          const bNum = Number.parseInt(b.version.replace(/^V/i, ''), 10) || 0;
          return aNum - bNum;
        });
        setAllVersions(sorted);
      })
      .catch(() => setAllVersions([]))
      .finally(() => setVersionsLoading(false));
  }, [template?.templateKey]);

  useEffect(() => {
    fetchAllVersions();
  }, [fetchAllVersions]);

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
        // Refresh the versions list to reflect the new published state
        fetchAllVersions();
      },
      failureCallback: (err: any) => {
        setError(err?.message ?? 'Failed to publish template');
      },
    });
  }, [id, template, fetchAllVersions]);

  const SUCCESS_ALERT_DURATION_MS = 5000;
  useEffect(() => {
    if (!publishSuccess) return;
    const timer = globalThis.setTimeout(() => setPublishSuccess(false), SUCCESS_ALERT_DURATION_MS);
    return () => globalThis.clearTimeout(timer);
  }, [publishSuccess]);

  useEffect(() => {
    if (!createProcessModelSuccess) return;
    const timer = globalThis.setTimeout(() => setCreateProcessModelSuccess(null), SUCCESS_ALERT_DURATION_MS);
    return () => globalThis.clearTimeout(timer);
  }, [createProcessModelSuccess]);

  useEffect(() => {
    if (!saveVisibilitySuccess) return;
    const timer = globalThis.setTimeout(() => setSaveVisibilitySuccess(false), SUCCESS_ALERT_DURATION_MS);
    return () => globalThis.clearTimeout(timer);
  }, [saveVisibilitySuccess]);

  const handleVisibilityChange = useCallback(
    (visibility: TemplateVisibility) => {
      if (!template) return;
      if (visibility === template.visibility) {
        setPendingVisibility(null);
      } else {
        setPendingVisibility(visibility);
      }
    },
    [template],
  );

  const handleSaveVisibility = useCallback(() => {
    if (!template || isNaN(id) || !pendingVisibility) return;
    setError(null);
    setIsSavingVisibility(true);
    TemplateService.updateTemplate(id, { visibility: pendingVisibility })
      .then((updated) => {
        setTemplate(updated);
        setPendingVisibility(null);
        setSaveVisibilitySuccess(true);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to update visibility');
      })
      .finally(() => {
        setIsSavingVisibility(false);
      });
  }, [id, template, pendingVisibility]);

  const handleCreateProcessModelSuccess = useCallback((processModelId: string) => {
    setCreateProcessModelSuccess(processModelId);
    // Navigate to the new process model after a short delay
    setTimeout(() => {
      const encodedId = processModelId.replaceAll('/', ':');
      navigate(`/process-models/${encodedId}`);
    }, 1500);
  }, [navigate]);

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
        <Button component={Link} to="/templates" startIcon={<ArrowBackIcon />} variant="text" sx={{ mb: 2 }}>
          {t("back_to_templates")}
        </Button>
      </Box>
    );
  }

  if (!template) {
    return null;
  }

  const breadcrumbs = [
    [t("templates"), '/templates'],
    [template.name, `/templates/${templateId}`],
  ];

  return (
    <Box sx={{ px: 2, pl: 3, pb: 3 }}>
      <Box sx={{ mb: 1 }}>
        <ProcessBreadcrumb hotCrumbs={breadcrumbs} />
      </Box>
      {allVersions.length > 1 && (
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
          <FormControl size="small" sx={{ minWidth: 280 }} disabled={versionsLoading}>
            <InputLabel id="template-version-label">{t("all_versions")}</InputLabel>
            <Select
              labelId="template-version-label"
              label={t("all_versions")}
              data-testid="template-version-select"
              value={template.id}
              onChange={(e) => {
                const selectedId = Number(e.target.value);
                if (selectedId !== template.id) navigate(`/templates/${selectedId}`);
              }}
              renderValue={(selectedId) => {
                const selected = allVersions.find((v) => v.id === selectedId);
                if (!selected) return '';
                return (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <span>{selected.version}</span>
                    {selected.isPublished && (
                      <Chip label={t("published")} size="small" color="success" sx={{ height: 20 }} />
                    )}
                    {!selected.isPublished && (
                      <Chip label={t("draft")} size="small" variant="outlined" sx={{ height: 20 }} />
                    )}
                  </Box>
                );
              }}
            >
              {allVersions.map((v) => (
                <MenuItem key={v.id} value={v.id}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                    <span>{v.version}</span>
                    {v.isPublished && (
                      <Chip label={t("published")} size="small" color="success" sx={{ height: 20 }} />
                    )}
                    {!v.isPublished && (
                      <Chip label={t("draft")} size="small" variant="outlined" sx={{ height: 20 }} />
                    )}
                    {v.id === template.id && (
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                        {t("current")}
                      </Typography>
                    )}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Paper>
      )}
      <TemplateDetailsCard
        template={template}
        onExport={handleExport}
        onPublish={handlePublish}
        onCreateProcessModel={() => setCreateProcessModelOpen(true)}
        pendingVisibility={pendingVisibility}
        onVisibilityChange={handleVisibilityChange}
        onSaveVisibility={handleSaveVisibility}
        isSaving={isSavingVisibility}
      />
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
      {saveVisibilitySuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setSaveVisibilitySuccess(false)}>
          Visibility updated successfully.
        </Alert>
      )}
      {createProcessModelSuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setCreateProcessModelSuccess(null)}>
          Process model created successfully! Redirecting to {createProcessModelSuccess}...
        </Alert>
      )}

      <CreateProcessModelFromTemplateModal
        open={createProcessModelOpen}
        onClose={() => setCreateProcessModelOpen(false)}
        template={template}
        onSuccess={handleCreateProcessModelSuccess}
      />
    </Box>
  );
}
