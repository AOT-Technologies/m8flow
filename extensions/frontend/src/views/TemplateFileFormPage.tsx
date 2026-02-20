import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  CircularProgress,
  Alert,
  Stack,
  Typography,
  Chip,
  Snackbar,
} from "@mui/material";
import ProcessBreadcrumb from "@spiffworkflow-frontend/components/ProcessBreadcrumb";
import { Editor } from "@monaco-editor/react";
import MDEditor from "@uiw/react-md-editor";
import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";
import type { Template } from "../types/template";
import { normalizeTemplate } from "../utils/templateHelpers";
import UserService from "../services/UserService";

export default function TemplateFileFormPage() {
  const { templateId, fileName } = useParams<{
    templateId: string;
    fileName: string;
  }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [fileLoaded, setFileLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [newVersionInfo, setNewVersionInfo] = useState<{
    id: number;
    version: string;
  } | null>(null);
  const isViewer = UserService.isViewer();

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const id = templateId ? Number.parseInt(templateId, 10) : NaN;
  const decodedFileName = fileName ? decodeURIComponent(fileName) : "";
  const lower = decodedFileName.toLowerCase();
  const isJson = lower.endsWith(".json");
  const isMd = lower.endsWith(".md");

  // Cleanup save success timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

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
        setFileLoaded(true);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load file");
        setLoading(false);
      });
  }, [templateId, id, fileName, decodedFileName]);

  const handleSave = () => {
    if (isNaN(id)) return;
    setError(null);
    const contentType = isMd ? "text/markdown" : "text/plain";
    TemplateService.updateTemplateFile(
      id,
      decodedFileName,
      fileContent,
      contentType,
    )
      .then((updatedTemplate) => {
        // Check if a new version was created (template ID changed)
        if (updatedTemplate.id !== id) {
          setNewVersionInfo({
            id: updatedTemplate.id,
            version: updatedTemplate.version,
          });
          // Navigate to the new version after a short delay
          setTimeout(() => {
            navigate(
              `/templates/${updatedTemplate.id}/form/${encodeURIComponent(decodedFileName)}`,
            );
          }, 2000);
        } else {
          setSaveSuccess(true);
          if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
          saveTimerRef.current = setTimeout(() => setSaveSuccess(false), 3000);
        }
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Save failed";
        setError(message);
      });
  };

  const handleDelete = () => {
    if (isNaN(id)) return;
    const confirmMsg = template?.isPublished
      ? `Delete file "${decodedFileName}"? A new draft version will be created.`
      : `Delete file "${decodedFileName}"? This cannot be undone.`;
    if (!globalThis.confirm(confirmMsg)) return;
    setError(null);
    TemplateService.deleteTemplateFile(id, decodedFileName)
      .then(() => {
        navigate(`/templates/${id}`);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Delete failed"),
      );
  };

  const handleDownload = () => {
    if (isNaN(id)) return;
    TemplateService.downloadTemplateFile(id, decodedFileName).catch((err) =>
      setError(err instanceof Error ? err.message : "Download failed"),
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !fileLoaded) {
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

  const hotCrumbs: [string, string?][] = [
    ["Templates", "/templates"],
    [template?.name ?? "Template", `/templates/${id}`],
    [decodedFileName],
  ];

  const editorLanguage = isJson ? "json" : isMd ? "markdown" : "plaintext";

  return (
    <Box sx={{ p: 2, pl: 3, maxWidth: "100%", overflow: "hidden" }}>
      <Box sx={{ mb: 1 }}>
        <ProcessBreadcrumb hotCrumbs={hotCrumbs} />
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1 }}>
        <Typography variant="h5" component="h1">
          Template File: {decodedFileName}
        </Typography>
        {template?.isPublished && (
          <Chip label="Published" color="success" size="small" />
        )}
      </Box>
      {template?.isPublished && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          This template is published. Saving changes will create a new draft
          version.
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {saveSuccess && (
        <Alert
          severity="success"
          sx={{ mb: 1 }}
          onClose={() => setSaveSuccess(false)}
        >
          File saved successfully.
        </Alert>
      )}
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <Button variant="contained" color="primary" onClick={handleSave}>
          Save
        </Button>
        <Button variant="contained" color="error" onClick={handleDelete}>
          Delete
        </Button>
        {!isViewer && (
          <>
            <Button variant="contained" color="primary" onClick={handleSave}>
              Save
            </Button>
            <Button variant="contained" color="error" onClick={handleDelete}>
              Delete
            </Button>
          </>
        )}
        <Button variant="outlined" onClick={handleDownload}>
          Download
        </Button>
      </Stack>
      <Snackbar
        open={!!newVersionInfo}
        autoHideDuration={4000}
        onClose={() => setNewVersionInfo(null)}
        message={`A new draft version (${newVersionInfo?.version}) was created because the template was published. Redirecting...`}
      />
      {isMd ? (
        <div data-color-mode="light">
          <MDEditor
            height={600}
            highlightEnable={false}
            value={fileContent}
            onChange={(v) => setFileContent(v ?? "")}
          />
        </div>
      ) : (
        <Editor
          height={600}
          width="100%"
          defaultLanguage={editorLanguage}
          value={fileContent}
          onChange={(v) => setFileContent(v ?? "")}
        />
      )}
    </Box>
  );
}
