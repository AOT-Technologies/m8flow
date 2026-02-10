import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Box, Button, CircularProgress, Alert } from "@mui/material";
import ProcessBreadcrumb from "@spiffworkflow-frontend/components/ProcessBreadcrumb";
import ReactDiagramEditor from "@spiffworkflow-frontend/components/ReactDiagramEditor";
import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";
import type { Template } from "../types/template";
import { normalizeTemplate } from "../utils/templateHelpers";

const noop = () => {};
const DIAGRAM_EDITOR_NOOP_PROPS = {
  onLaunchBpmnEditor: noop,
  onLaunchDmnEditor: noop,
  onLaunchMarkdownEditor: noop,
  onLaunchScriptEditor: noop,
  onLaunchMessageEditor: noop,
  onSearchProcessModels: noop,
  onDataStoresRequested: noop,
  onMessagesRequested: noop,
  onServiceTasksRequested: noop,
};

function getFirstBpmnFileName(template: Template | null): string | null {
  const files = template?.files ?? [];
  const first = files.find((f) => (f.fileType ?? "").toLowerCase() === "bpmn");
  return first?.fileName ?? null;
}

export default function TemplateFileDiagramPage() {
  const { templateId, fileName } = useParams<{ templateId: string; fileName: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [diagramHasChanges, setDiagramHasChanges] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const id = templateId ? parseInt(templateId, 10) : NaN;
  const decodedFileName = fileName ? decodeURIComponent(fileName) : "";
  const firstBpmnFileName = getFirstBpmnFileName(template);

  // Cleanup save success timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);
  const isFirstBpmn =
    decodedFileName.toLowerCase().endsWith(".bpmn") &&
    firstBpmnFileName !== null &&
    decodedFileName === firstBpmnFileName;

  useEffect(() => {
    if (!templateId || !fileName || isNaN(id)) {
      setError("Invalid template or file");
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
      },
      failureCallback: () => {
        // Template name is used for breadcrumb; fall back to generic name
        setTemplate(null);
      },
    });

    TemplateService.getTemplateFileContent(id, decodedFileName)
      .then((text) => {
        setFileContent(text);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load file");
        setLoading(false);
      });
  }, [templateId, id, fileName, decodedFileName]);

  const saveDiagram = useCallback(
    (xml: string) => {
      if (isNaN(id)) return;
      setError(null);
      setSaveSuccess(false);
      const isBpmn = decodedFileName.toLowerCase().endsWith(".bpmn");
      if (isBpmn) {
        HttpService.makeCallToBackend({
          path: `/v1.0/m8flow/templates/${id}`,
          httpMethod: HttpService.HttpMethods.PUT,
          extraHeaders: {
            "Content-Type": "application/xml",
            "X-Template-File-Name": decodedFileName,
          },
          postBody: xml,
          successCallback: () => {
            setFileContent(xml);
            setDiagramHasChanges(false);
            setSaveSuccess(true);
            if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
            saveTimerRef.current = setTimeout(() => setSaveSuccess(false), 3000);
          },
          failureCallback: (err: unknown) => {
            setError(err instanceof Error ? err.message : "Save failed");
          },
        });
      } else {
        TemplateService.updateTemplateFile(id, decodedFileName, xml, "application/xml")
          .then(() => {
            setFileContent(xml);
            setDiagramHasChanges(false);
            setSaveSuccess(true);
            if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
            saveTimerRef.current = setTimeout(() => setSaveSuccess(false), 3000);
          })
          .catch((err) => setError(err instanceof Error ? err.message : "Save failed"));
      }
    },
    [id, decodedFileName]
  );

  const onElementsChanged = useCallback(() => {
    setDiagramHasChanges(true);
  }, []);

  // Provide JSON schema files from the template's file list to the BPMN modeler's
  // properties panel dropdown (matches ProcessModelEditDiagram's pattern: *-schema.json).
  const onJsonSchemaFilesRequested = useCallback(
    (event: any) => {
      const re = /.*[-.]schema\.json$/i;
      const jsonFiles = (template?.files ?? []).filter(
        (f) => f.fileName && re.test(f.fileName)
      );
      const options = jsonFiles.map((f) => ({
        label: f.fileName,
        value: f.fileName,
      }));
      event.eventBus.fire("spiff.json_schema_files.returned", { options });
    },
    [template]
  );

  // Provide DMN files from the template's file list to the BPMN modeler dropdown.
  const onDmnFilesRequested = useCallback(
    (event: any) => {
      const dmnFiles = (template?.files ?? []).filter(
        (f) => (f.fileType ?? "").toLowerCase() === "dmn"
      );
      const options = dmnFiles.map((f) => ({
        label: f.fileName,
        value: f.fileName,
      }));
      event.eventBus.fire("spiff.dmn_files.returned", { options });
    },
    [template]
  );

  // Navigate to the template form editor page when "Launch Editor" is clicked
  // in the BPMN modeler properties panel (for JSON schema files).
  const onLaunchJsonSchemaEditor = useCallback(
    (_element: any, schemaFileName: string, _eventBus: any) => {
      if (!isNaN(id) && schemaFileName) {
        navigate(
          `/templates/${id}/form/${encodeURIComponent(schemaFileName)}`
        );
      }
    },
    [id, navigate]
  );

  if (loading && !fileContent) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
        <Button onClick={() => navigate(`/templates/${id}`)} sx={{ mt: 2 }}>
          Back to Template
        </Button>
      </Box>
    );
  }

  if (!fileContent) {
    return null;
  }

  const lower = decodedFileName.toLowerCase();
  const diagramType = lower.endsWith(".dmn") ? "dmn" : "bpmn";
  const hotCrumbs: [string, string?][] = [
    ["Templates", "/templates"],
    [template?.name ?? "Template", `/templates/${id}`],
    [decodedFileName],
  ];

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: "60vh",
        overflow: "hidden",
        px: 2,
        pl: 3,
      }}
    >
      <Box sx={{ mb: 1 }}>
        <ProcessBreadcrumb hotCrumbs={hotCrumbs} />
      </Box>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {saveSuccess && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setSaveSuccess(false)}>
          File saved successfully.
        </Alert>
      )}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          pl: 2,
        }}
      >
        <Box className="template-modeler-editor-wrap" sx={{ flexShrink: 0 }}>
          <ReactDiagramEditor
            key={`template-file-${id}-${decodedFileName}`}
            diagramType={diagramType}
            diagramXML={fileContent}
            processModelId={`template-${id}`}
            fileName={decodedFileName}
            disableSaveButton={!diagramHasChanges}
            saveDiagram={saveDiagram}
            onElementsChanged={onElementsChanged}
            onJsonSchemaFilesRequested={onJsonSchemaFilesRequested}
            onDmnFilesRequested={onDmnFilesRequested}
            onLaunchJsonSchemaEditor={onLaunchJsonSchemaEditor}
            {...DIAGRAM_EDITOR_NOOP_PROPS}
          />
        </Box>
        <div
          id="diagram-container"
          style={{
            flex: 1,
            minHeight: 400,
            position: "relative",
          }}
        />
      </Box>
    </Box>
  );
}
