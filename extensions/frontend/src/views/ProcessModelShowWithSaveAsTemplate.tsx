import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { Box, Button } from "@mui/material";
import ProcessModelShow from "@spiffworkflow-frontend/views/ProcessModelShow";
import HttpService from "../services/HttpService";
import { modifyProcessIdentifierForPathParam } from "../helpers";
import { sortFilesWithPrimaryFirst } from "../utils/templateHelpers";
import SaveAsTemplateModal from "../components/SaveAsTemplateModal";
import type { SaveAsTemplateFile } from "../components/SaveAsTemplateModal";

const SUPPORTED_EXT = [".bpmn", ".json", ".dmn", ".md"];

function isSupportedFileName(name: string): boolean {
  const lower = name.toLowerCase();
  return SUPPORTED_EXT.some((ext) => lower.endsWith(ext));
}

/**
 * Wraps ProcessModelShow and adds a "Save as Template" button on the Process Model page.
 * When clicked, opens a modal to save all supported process-model files (.bpmn, .json, .dmn, .md) as a template.
 */
export default function ProcessModelShowWithSaveAsTemplate() {
  const params = useParams<{ process_model_id: string }>();
  const [saveAsTemplateOpen, setSaveAsTemplateOpen] = useState(false);

  const modifiedProcessModelId = params.process_model_id
    ? modifyProcessIdentifierForPathParam(params.process_model_id)
    : "";

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

  return (
    <Box sx={{ position: "relative", padding: "16px" }}>
      <ProcessModelShow />
      <Box sx={{ position: "absolute", top: 16, right: 16, zIndex: 10 }}>
        <Button
          variant="contained"
          onClick={() => setSaveAsTemplateOpen(true)}
          data-testid="save-as-template-button"
        >
          Save as Template
        </Button>
      </Box>
      <SaveAsTemplateModal
        open={saveAsTemplateOpen}
        onClose={() => setSaveAsTemplateOpen(false)}
        onSuccess={() => setSaveAsTemplateOpen(false)}
        getFiles={getFiles}
      />
    </Box>
  );
}
