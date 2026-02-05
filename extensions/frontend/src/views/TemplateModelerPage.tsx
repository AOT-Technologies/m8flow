import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Button, Chip, CircularProgress, Alert, Typography, Paper } from '@mui/material';
import ProcessBreadcrumb from '@spiffworkflow-frontend/components/ProcessBreadcrumb';
import ReactDiagramEditor from '@spiffworkflow-frontend/components/ReactDiagramEditor';
import DateAndTimeService from '@spiffworkflow-frontend/services/DateAndTimeService';
import HttpService from '../services/HttpService';
import { Template } from '../types/template';
import './TemplateModelerPage.css';

const DEFAULT_FILE_NAME = 'template.bpmn';

const noop = () => {};
const DIAGRAM_EDITOR_NOOP_PROPS = {
  onLaunchBpmnEditor: noop,
  onLaunchDmnEditor: noop,
  onLaunchJsonSchemaEditor: noop,
  onLaunchMarkdownEditor: noop,
  onLaunchScriptEditor: noop,
  onLaunchMessageEditor: noop,
  onSearchProcessModels: noop,
  onDataStoresRequested: noop,
  onDmnFilesRequested: noop,
  onJsonSchemaFilesRequested: noop,
  onMessagesRequested: noop,
  onServiceTasksRequested: noop,
};

function TemplateDetailsCard({ template }: { template: Template }) {
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
    </Paper>
  );
}

export default function TemplateModelerPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [bpmnXml, setBpmnXml] = useState<string | null>(null);
  const [diagramHasChanges, setDiagramHasChanges] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [publishSuccess, setPublishSuccess] = useState(false);

  const id = templateId ? parseInt(templateId, 10) : NaN;
  const fileName = DEFAULT_FILE_NAME;

  useEffect(() => {
    if (!templateId || isNaN(id)) {
      setError('Invalid template ID');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setBpmnXml(null);

    HttpService.makeCallToBackend({
      path: `/v1.0/m8flow/templates/${id}`,
      httpMethod: HttpService.HttpMethods.GET,
      successCallback: (result: Template) => {
        setTemplate(result);
        const content = result.bpmnContent ?? null;
        const hasContent = typeof content === 'string' && content.trim().length > 0;
        if (hasContent) {
          setBpmnXml(content);
          setLoading(false);
        } else {
          // Fallback: fetch raw BPMN from dedicated endpoint (e.g. if get response omits bpmnContent)
          HttpService.fetchTextFromBackend(
            `/v1.0/m8flow/templates/${id}/bpmn`,
            (xml) => {
              setBpmnXml(xml && xml.trim() ? xml : null);
              setLoading(false);
            },
            () => {
              setBpmnXml(null);
              setLoading(false);
            },
          );
        }
      },
      failureCallback: (err: any) => {
        setError(err?.message ?? 'Failed to load template');
        setLoading(false);
      },
    });
  }, [templateId, id]);

  const saveDiagram = useCallback(
    (xml: string) => {
      if (!template || isNaN(id)) return;

      setSaveSuccess(false);

      HttpService.makeCallToBackend({
        path: `/v1.0/m8flow/templates/${id}`,
        httpMethod: HttpService.HttpMethods.PUT,
        extraHeaders: { 'Content-Type': 'application/xml' },
        postBody: xml,
        successCallback: (result: Template) => {
          setTemplate(result);
          setBpmnXml(result.bpmnContent ?? xml);
          setDiagramHasChanges(false);
          setSaveSuccess(true);
        },
        failureCallback: (err: any) => {
          setError(err?.message ?? 'Failed to save template');
        },
      });
    },
    [id, template],
  );

  const onElementsChanged = useCallback(() => {
    setDiagramHasChanges(true);
  }, []);

  const handlePublish = useCallback(() => {
    if (!template || isNaN(id)) return;
    setPublishSuccess(false);
    setError(null);
    HttpService.makeCallToBackend({
      path: `/v1.0/m8flow/templates/${id}`,
      httpMethod: HttpService.HttpMethods.PUT,
      postBody: { is_published: true },
      successCallback: (result: Template) => {
        setTemplate(result);
        setPublishSuccess(true);
      },
      failureCallback: (err: any) => {
        setError(err?.message ?? 'Failed to publish template');
      },
    });
  }, [id, template]);

  const SUCCESS_ALERT_DURATION_MS = 5000;
  useEffect(() => {
    if (!saveSuccess && !publishSuccess) return;
    const timer = window.setTimeout(() => {
      setSaveSuccess(false);
      setPublishSuccess(false);
    }, SUCCESS_ALERT_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [saveSuccess, publishSuccess]);

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

  const hasBpmn = typeof bpmnXml === 'string' && bpmnXml.trim().length > 0;
  if (!hasBpmn) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          This template has no BPMN content to display.
        </Alert>
        <Button onClick={() => navigate('/templates')} sx={{ mt: 2 }}>
          Back to Templates
        </Button>
      </Box>
    );
  }

  const hotCrumbs: [string, string?][] = [
    ['Templates', '/templates'],
    [template.name],
    [fileName],
  ];

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '60vh',
        overflow: 'hidden',
        px: 2,
        pl: 3,
      }}
    >
      {/* Row 1: Breadcrumb only */}
      <Box sx={{ mb: 1 }}>
        <ProcessBreadcrumb hotCrumbs={hotCrumbs} />
      </Box>

      {/* Row 2: Template details below breadcrumb, above button row */}
      <TemplateDetailsCard template={template} />

      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {saveSuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setSaveSuccess(false)}>
          Template saved successfully.
        </Alert>
      )}

      {publishSuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setPublishSuccess(false)}>
          Template published successfully.
        </Alert>
      )}

      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          pl: 2,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'flex-start',
            gap: 2,
            flexShrink: 0,
          }}
        >
          <Box className="template-modeler-editor-wrap" sx={{ flexShrink: 0 }}>
            <ReactDiagramEditor
              key={`template-modeler-${id}`}
              diagramType="bpmn"
              diagramXML={bpmnXml}
              processModelId={`template-${id}`}
              fileName={fileName}
              disableSaveButton={!diagramHasChanges}
              saveDiagram={saveDiagram}
              onElementsChanged={onElementsChanged}
              {...DIAGRAM_EDITOR_NOOP_PROPS}
            />
          </Box>
          {!template.isPublished && (
            <Box sx={{ mt: 2 }}>
              <Button size="small" variant="contained" color="primary" onClick={handlePublish}>
                Publish
              </Button>
            </Box>
          )}
        </Box>
        <div
          id="diagram-container"
          style={{
            flex: 1,
            minHeight: 400,
            position: 'relative',
          }}
        />
      </Box>
    </Box>
  );
}
