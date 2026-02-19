import { BACKEND_BASE_URL } from "@spiffworkflow-frontend/config";
import HttpService, { getBasicHeaders } from "./HttpService";
import type {
  CreateTemplateMetadata,
  CreateProcessModelFromTemplateRequest,
  CreateProcessModelFromTemplateResponse,
  ProcessModelTemplateInfo,
  Template,
  TemplateFile,
} from "../types/template";

const BASE_PATH = "/v1.0/m8flow";

function backendPath(path: string): string {
  const p = path.replace(/^\/v1\.0/, "");
  return `${BACKEND_BASE_URL}${p}`;
}

function buildHeaders(metadata: CreateTemplateMetadata): Record<string, string> {
  const headers: Record<string, string> = {
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

function secondsFromApiOrIso(seconds: unknown, iso: unknown): number {
  if (typeof seconds === "number" && !Number.isNaN(seconds)) return seconds;
  if (typeof iso === "string") {
    const ms = Date.parse(iso);
    if (!Number.isNaN(ms)) return Math.floor(ms / 1000);
  }
  return 0;
}

function parseTemplateResponse(data: Record<string, unknown>): Template {
  const createdAtInSeconds = secondsFromApiOrIso(data.createdAtInSeconds, data.createdAt);
  const updatedAtInSeconds = secondsFromApiOrIso(data.updatedAtInSeconds, data.updatedAt);
  return {
    ...data,
    files: (data.files as TemplateFile[]) ?? [],
    createdAtInSeconds,
    updatedAtInSeconds,
  } as Template;
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
    const extraHeaders = {
      ...buildHeaders(metadata),
      "Content-Type": "application/xml",
    };
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates`,
        httpMethod: "POST",
        postBody: bpmnXml,
        extraHeaders,
        successCallback: (data: Record<string, unknown>) =>
          resolve(parseTemplateResponse(data)),
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

  /**
   * Create a template with multiple files (multipart). At least one BPMN required.
   */
  createTemplateWithFiles(
    metadata: CreateTemplateMetadata,
    files: { name: string; content: Blob | File }[]
  ): Promise<Template> {
    if (!metadata.template_key?.trim() || !metadata.name?.trim()) {
      return Promise.reject(
        new Error("Template key and name are required")
      );
    }
    if (!files.length) {
      return Promise.reject(new Error("At least one file is required"));
    }
    const form = new FormData();
    files.forEach((f) => form.append("files", f.content, f.name));
    const headers = { ...getBasicHeaders(), ...buildHeaders(metadata) };
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", backendPath(`${BASE_PATH}/templates`));
      xhr.withCredentials = true;
      Object.keys(headers).forEach((k) => xhr.setRequestHeader(k, headers[k]));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText) as Record<string, unknown>;
            resolve(parseTemplateResponse(data));
          } catch {
            reject(new Error("Invalid response"));
          }
        } else {
          let msg = "Failed to create template";
          try {
            const err = JSON.parse(xhr.responseText);
            if (err?.message) msg = err.message;
          } catch {
            // ignore
          }
          reject(new Error(msg));
        }
      };
      xhr.onerror = () => reject(new Error("Network error"));
      xhr.send(form);
    });
  },

  getTemplateById(
    id: number,
    includeContents = true
  ): Promise<Template> {
    const q = includeContents ? "?include_contents=true" : "?include_contents=false";
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates/${id}${q}`,
        httpMethod: "GET",
        successCallback: (data: Record<string, unknown>) =>
          resolve(parseTemplateResponse(data)),
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to fetch template";
          reject(new Error(message));
        },
      });
    });
  },

  updateTemplate(
    id: number,
    updates: Record<string, unknown>,
    bpmnXml?: string
  ): Promise<Template> {
    const extraHeaders: Record<string, string> = {};
    if (bpmnXml !== undefined) {
      extraHeaders["Content-Type"] = "application/xml";
    }
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates/${id}`,
        httpMethod: "PUT",
        postBody: bpmnXml !== undefined ? bpmnXml : JSON.stringify(updates),
        extraHeaders:
          Object.keys(extraHeaders).length > 0 ? extraHeaders : undefined,
        successCallback: (data: Record<string, unknown>) =>
          resolve(parseTemplateResponse(data)),
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to update template";
          reject(new Error(message));
        },
      });
    });
  },

  getTemplateFileUrl(id: number, fileName: string): string {
    return backendPath(
      `${BASE_PATH}/templates/${id}/files/${encodeURIComponent(fileName)}`
    );
  },

  /**
   * Fetch a template file as text (for in-app viewer). Uses auth headers.
   */
  getTemplateFileContent(id: number, fileName: string): Promise<string> {
    const url = backendPath(
      `${BASE_PATH}/templates/${id}/files/${encodeURIComponent(fileName)}`
    );
    return fetch(url, {
      credentials: "include",
      headers: new Headers(HttpService.getBasicHeaders()),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to load file");
      return r.text();
    });
  },

  /**
   * Update a template file by name. Uses auth headers.
   * If the template is published, a new draft version is created.
   * Returns the template that was actually updated (may be a new version).
   */
  updateTemplateFile(
    id: number,
    fileName: string,
    content: string,
    contentType?: string
  ): Promise<Template> {
    const url = backendPath(
      `${BASE_PATH}/templates/${id}/files/${encodeURIComponent(fileName)}`
    );
    const headers = new Headers(HttpService.getBasicHeaders());
    if (contentType) headers.set("Content-Type", contentType);
    return fetch(url, {
      method: "PUT",
      credentials: "include",
      headers,
      body: content,
    }).then((r) => {
      if (!r.ok) throw new Error("Update failed");
      return r.json();
    }).then((data: Record<string, unknown>) => parseTemplateResponse(data));
  },

  /**
   * Delete a template file by name. Uses auth headers.
   * If the template is published, a new draft version is created and the file is deleted there.
   */
  deleteTemplateFile(id: number, fileName: string): Promise<void> {
    const url = backendPath(
      `${BASE_PATH}/templates/${id}/files/${encodeURIComponent(fileName)}`
    );
    return fetch(url, {
      method: "DELETE",
      credentials: "include",
      headers: new Headers(HttpService.getBasicHeaders()),
    }).then((r) => {
      if (!r.ok) throw new Error("Delete failed");
    });
  },

  /**
   * Soft-delete a template by ID. Uses auth headers. Template must not be published.
   */
  deleteTemplate(id: number): Promise<void> {
    const url = backendPath(`${BASE_PATH}/templates/${id}`);
    return fetch(url, {
      method: "DELETE",
      credentials: "include",
      headers: new Headers(HttpService.getBasicHeaders()),
    }).then((r) => {
      if (!r.ok) throw new Error("Delete failed");
    });
  },

  /**
   * Fetch a template file as blob and trigger browser download. Uses auth headers.
   */
  downloadTemplateFile(id: number, fileName: string): Promise<void> {
    const url = backendPath(
      `${BASE_PATH}/templates/${id}/files/${encodeURIComponent(fileName)}`
    );
    return fetch(url, {
      credentials: "include",
      headers: new Headers(HttpService.getBasicHeaders()),
    }).then((r) => {
      if (!r.ok) throw new Error("Download failed");
      return r.blob();
    }).then((blob) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    });
  },

  exportTemplate(id: number): Promise<Blob> {
    return fetch(backendPath(`${BASE_PATH}/templates/${id}/export`), {
      credentials: "include",
      headers: new Headers(HttpService.getBasicHeaders()),
    }).then((r) => {
      if (!r.ok) throw new Error("Export failed");
      return r.blob();
    });
  },

  /**
   * Fetch published versions of a template by template key.
   * Uses GET /templates?template_key=...&published_only=true&latest_only=false.
   */
  getPublishedVersions(templateKey: string): Promise<Template[]> {
    const query = new URLSearchParams({
      template_key: templateKey,
      published_only: "true",
      latest_only: "false",
    }).toString();
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates?${query}`,
        httpMethod: "GET",
        successCallback: (result: Record<string, unknown>) => {
          const results = result.results as Record<string, unknown>[];
          resolve(
            Array.isArray(results)
              ? results.map((r) => parseTemplateResponse(r))
              : []
          );
        },
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to fetch published versions";
          reject(new Error(message));
        },
      });
    });
  },

  /**
   * Fetch all versions of a template by template key (both published and draft).
   * Uses GET /templates?template_key=...&latest_only=false.
   */
  getAllVersions(templateKey: string): Promise<Template[]> {
    const query = new URLSearchParams({
      template_key: templateKey,
      latest_only: "false",
    }).toString();
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates?${query}`,
        httpMethod: "GET",
        successCallback: (result: Record<string, unknown>) => {
          const results = result.results as Record<string, unknown>[];
          resolve(
            Array.isArray(results)
              ? results.map((r) => parseTemplateResponse(r))
              : []
          );
        },
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to fetch template versions";
          reject(new Error(message));
        },
      });
    });
  },

  importTemplate(
    zipFile: File,
    metadata: CreateTemplateMetadata
  ): Promise<Template> {
    if (!metadata.template_key?.trim() || !metadata.name?.trim()) {
      return Promise.reject(
        new Error("Template key and name are required")
      );
    }
    const form = new FormData();
    form.append("file", zipFile);
    const headers = { ...HttpService.getBasicHeaders(), ...buildHeaders(metadata) };
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", backendPath(`${BASE_PATH}/templates/import`));
      xhr.withCredentials = true;
      Object.keys(headers).forEach((k) => xhr.setRequestHeader(k, headers[k]));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText) as Record<string, unknown>;
            resolve(parseTemplateResponse(data));
          } catch {
            reject(new Error("Invalid response"));
          }
        } else {
          let msg = "Import failed";
          try {
            const err = JSON.parse(xhr.responseText);
            if (err?.message) msg = err.message;
          } catch {
            // ignore
          }
          reject(new Error(msg));
        }
      };
      xhr.onerror = () => reject(new Error("Network error"));
      xhr.send(form);
    });
  },

  /**
   * Create a process model from a template.
   */
  createProcessModelFromTemplate(
    templateId: number,
    request: CreateProcessModelFromTemplateRequest
  ): Promise<CreateProcessModelFromTemplateResponse> {
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/templates/${templateId}/create-process-model`,
        httpMethod: "POST",
        postBody: request,
        successCallback: (data: CreateProcessModelFromTemplateResponse) => resolve(data),
        failureCallback: (err: unknown) => {
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to create process model from template";
          reject(new Error(message));
        },
      });
    });
  },

  /**
   * Get template provenance info for a process model.
   * Returns null if the process model was not created from a template.
   */
  getProcessModelTemplateInfo(
    processModelIdentifier: string
  ): Promise<ProcessModelTemplateInfo | null> {
    // Convert slashes to colons for the API path
    const modifiedId = processModelIdentifier.replaceAll("/", ":");
    return new Promise((resolve, reject) => {
      HttpService.makeCallToBackend({
        path: `${BASE_PATH}/process-models/${modifiedId}/template-info`,
        httpMethod: "GET",
        successCallback: (data: ProcessModelTemplateInfo) => resolve(data),
        failureCallback: (err: unknown) => {
          // 404 means no template info exists - not an error
          if (err && typeof err === "object" && "status_code" in err) {
            const statusCode = (err as { status_code: unknown }).status_code;
            if (statusCode === 404) {
              resolve(null);
              return;
            }
          }
          const message =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: unknown }).message)
              : "Failed to get template info";
          reject(new Error(message));
        },
      });
    });
  },
};

export default TemplateService;
