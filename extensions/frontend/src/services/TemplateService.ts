import HttpService from "@spiffworkflow-frontend/services/HttpService";
import type { CreateTemplateMetadata, Template } from "../types/template";

const BASE_PATH = "/v1.0/m8flow";

function buildHeaders(metadata: CreateTemplateMetadata): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/xml",
    "X-Template-Key": metadata.template_key.trim(),
    "X-Template-Name": metadata.name.trim(),
  };
  if (metadata.description !== undefined && metadata.description !== "") {
    headers["X-Template-Description"] = metadata.description;
  }
  if (metadata.category !== undefined && metadata.category !== "") {
    headers["X-Template-Category"] = metadata.category;
  }
  if (metadata.tags !== undefined) {
    const tags =
      Array.isArray(metadata.tags)
        ? metadata.tags
        : typeof metadata.tags === "string"
          ? metadata.tags.split(",").map((s) => s.trim()).filter(Boolean)
          : [];
    if (tags.length > 0) {
      headers["X-Template-Tags"] = JSON.stringify(tags);
    }
  }
  if (metadata.visibility !== undefined && metadata.visibility !== "") {
    headers["X-Template-Visibility"] = metadata.visibility;
  }
  if (metadata.status !== undefined && metadata.status !== "") {
    headers["X-Template-Status"] = metadata.status;
  }
  if (metadata.version !== undefined && metadata.version !== "") {
    headers["X-Template-Version"] = metadata.version;
  }
  if (metadata.is_published !== undefined) {
    headers["X-Template-Is-Published"] = metadata.is_published ? "true" : "false";
  }
  return headers;
}

const TemplateService = {
  /**
   * Create a template with BPMN XML body and metadata via X-Template-* headers.
   */
  createTemplate(
    bpmnXml: string,
    metadata: CreateTemplateMetadata
  ): Promise<Template> {
    if (!metadata.template_key?.trim() || !metadata.name?.trim()) {
      return Promise.reject(
        new Error("Template key and name are required")
      );
    }
    const extraHeaders = buildHeaders(metadata);
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates`,
        httpMethod: "POST",
        postBody: bpmnXml,
        extraHeaders,
        successCallback: resolve,
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to create template";
          reject(new Error(message));
        },
      });
    });
  },
};

export default TemplateService;
