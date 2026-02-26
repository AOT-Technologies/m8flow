import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Box, Button, Chip, Paper, Typography, CircularProgress } from "@mui/material";
import ProcessModelShow from "./ProcessModelShow";
import DateAndTimeService from "@spiffworkflow-frontend/services/DateAndTimeService";
import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";
import { modifyProcessIdentifierForPathParam } from "../helpers";
import { sortFilesWithPrimaryFirst } from "../utils/templateHelpers";
import SaveAsTemplateModal from "../components/SaveAsTemplateModal";
import type { SaveAsTemplateFile } from "../components/SaveAsTemplateModal";
import type { ProcessModelTemplateInfo } from "../types/template";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";

const SUPPORTED_EXT = [".bpmn", ".json", ".dmn", ".md"];

function isSupportedFileName(name: string): boolean {
  const lower = name.toLowerCase();
  return SUPPORTED_EXT.some((ext) => lower.endsWith(ext));
}

/**
 * Wraps ProcessModelShow and adds a "Save as Template" button on the Process Model page.
 * When clicked, opens a modal to save all supported process-model files (.bpmn, .json, .dmn, .md) as a template.
 * Also displays template provenance info if the process model was created from a template.
 */
export default function ProcessModelShowWithSaveAsTemplate() {
  const params = useParams<{ process_model_id: string }>();
  const [saveAsTemplateOpen, setSaveAsTemplateOpen] = useState(false);
  const [templateInfo, setTemplateInfo] = useState<ProcessModelTemplateInfo | null>(null);
  const [templateInfoLoading, setTemplateInfoLoading] = useState(false);
  const { ability, permissionsLoaded } = usePermissionFetcher({
    "/m8flow/templates": ["POST"],
  });

  const modifiedProcessModelId = params.process_model_id
    ? modifyProcessIdentifierForPathParam(params.process_model_id)
    : "";

  // Convert modified ID (with colons) back to standard format (with slashes) for the API
  const processModelIdentifier = params.process_model_id?.replaceAll(":", "/") || "";

  // Fetch template provenance info
  useEffect(() => {
    if (!processModelIdentifier) return;

    setTemplateInfoLoading(true);
    TemplateService.getProcessModelTemplateInfo(processModelIdentifier)
      .then((info) => {
        setTemplateInfo(info);
      })
      .catch(() => {
        // Silently ignore errors - just means no template info
        setTemplateInfo(null);
      })
      .finally(() => {
        setTemplateInfoLoading(false);
      });
  }, [processModelIdentifier]);

  const getFiles = (): Promise<SaveAsTemplateFile[]> => {
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `/process-models/${modifiedProcessModelId}`,
        httpMethod: "GET",
        successCallback: (model: {
          files?: { name?: string }[];
          primary_file_name?: string;
        }) => {
          const primaryName = model?.primary_file_name ?? "";
          const fileList = model?.files ?? [];
          const supported = fileList.filter((f) =>
            isSupportedFileName(f?.name ?? "")
          );
          if (supported.length === 0) {
            reject(new Error("No supported files (.bpmn, .json, .dmn, .md) in this process model"));
            return;
          }
          const results: SaveAsTemplateFile[] = [];
          let pending = supported.length;
          let hasError = false;
          supported.forEach((f) => {
            const fileName = f?.name ?? "";
            HttpService.makeCallToBackend({
              path: `/process-models/${modifiedProcessModelId}/files/${fileName}`,
              httpMethod: "GET",
              successCallback: (file: { file_contents?: string }) => {
                if (hasError) return;
                const content = file?.file_contents;
                const str =
                  typeof content === "string" ? content : "";
                const ext = fileName.toLowerCase().slice(fileName.lastIndexOf("."));
                const mime =
                  ext === ".json"
                    ? "application/json"
                    : ext === ".md"
                      ? "text/markdown"
                      : "application/xml";
                results.push({
                  name: fileName,
                  content: new Blob([str], { type: mime }),
                });
                pending -= 1;
                if (pending === 0) {
                  // Sort so the primary BPMN file is first in the list.
                  // This ensures the backend's get_first_bpmn_content() and
                  // the frontend's TemplateFileList both treat it as primary.
                  resolve(sortFilesWithPrimaryFirst(results, primaryName));
                }
              },
              failureCallback: () => {
                if (!hasError) {
                  hasError = true;
                  reject(new Error(`Failed to load file: ${fileName}`));
                }
              },
            });
          });
        },
        failureCallback: (err: unknown) => {
          reject(err instanceof Error ? err : new Error("Failed to load process model"));
        },
      });
    });
  };

  if (!permissionsLoaded) return null;

  return (
    <Box sx={{ position: "relative", padding: "16px" }}>
      <ProcessModelShow />
      {ability.can("POST", "/m8flow/templates") && (
        <Box sx={{ position: "absolute", top: 16, right: 16, zIndex: 10 }}>
          <Button
            variant="contained"
            onClick={() => setSaveAsTemplateOpen(true)}
            data-testid="save-as-template-button"
          >
            Save as Template
          </Button>
        </Box>
      )}

      {/* Template Provenance Info */}
      {templateInfoLoading && (
        <Box sx={{ mt: 2, display: "flex", alignItems: "center", gap: 1 }}>
          <CircularProgress size={16} />
          <Typography variant="caption" color="text.secondary">
            Loading template info...
          </Typography>
        </Box>
      )}
      {templateInfo && !templateInfoLoading && (
        <Paper
          elevation={0}
          sx={{
            mt: 2,
            p: 2,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            backgroundColor: "action.hover",
          }}
        >
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
            Created from Template
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, alignItems: "center" }}>
            <Link
              to={`/templates/${templateInfo.source_template_id}`}
              style={{ textDecoration: "none" }}
            >
              <Chip
                label={templateInfo.source_template_name}
                color="primary"
                size="small"
                clickable
              />
            </Link>
            <Chip
              label={`Version: ${templateInfo.source_template_version}`}
              variant="outlined"
              size="small"
            />
            <Chip
              label={`Key: ${templateInfo.source_template_key}`}
              variant="outlined"
              size="small"
            />
            <Typography variant="caption" color="text.secondary">
              Created by: {templateInfo.created_by}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Created: {DateAndTimeService.convertSecondsToFormattedDateTime(templateInfo.created_at_in_seconds) ?? "—"}
            </Typography>
          </Box>
        </Paper>
      )}
      <SaveAsTemplateModal
        open={saveAsTemplateOpen}
        onClose={() => setSaveAsTemplateOpen(false)}
        onSuccess={() => setSaveAsTemplateOpen(false)}
        getFiles={getFiles}
      />
    </Box>
  );
}
