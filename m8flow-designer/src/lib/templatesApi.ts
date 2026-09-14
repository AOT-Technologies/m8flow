import { apiFetch, API_BASE_URL } from './api';

/**
 * Client for m8flow-backend's already-live `/v1.0/m8flow/templates*`
 * contract (Template modeler map, ticket 01 —
 * `.scratch/template-modeler/`). Types and response shapes are read
 * directly from `templates_controller.py`'s own `_serialize_template`/
 * `template_list`/pagination code, not guessed from the
 * `m8flow-frontend` reference client (`TemplateService.ts`) — that
 * reference uses Spiff-style `HttpService`/XHR and is a UX/contract
 * pointer only, not a source to port. Response bodies are camelCase as-is
 * (unlike this app's other `/v1.0/m8flow/*` routes, which are
 * snake_case) — confirmed from the controller, no field-mapping needed.
 */

export type TemplateVisibility = 'PRIVATE' | 'TENANT' | 'PUBLIC';

export type TemplateFileType = 'bpmn' | 'json' | 'dmn' | 'md';

export type TemplateFile = {
  fileType: TemplateFileType;
  fileName: string;
};

export type TemplateTenant = {
  id: string;
  name: string;
  slug: string;
};

export type Template = {
  id: number;
  templateKey: string;
  version: string;
  name: string;
  description: string | null;
  tags: string[] | null;
  category: string | null;
  tenantId: string | null;
  /** Only present when the caller can see cross-tenant (PUBLIC) results. */
  tenant?: TemplateTenant;
  visibility: TemplateVisibility;
  files: TemplateFile[];
  /** Omitted from list responses (`include_contents=false`); present on GET-by-id by default. */
  bpmnContent?: string | null;
  isPublished: boolean;
  isDeleted?: boolean;
  status: string | null;
  createdBy: string;
  modifiedBy: string;
  createdAtInSeconds: number;
  updatedAtInSeconds: number;
};

export type TemplatePagination = {
  count: number;
  total: number;
  pages: number;
};

export type TemplateListResponse = {
  results: Template[];
  pagination: TemplatePagination;
};

export type TemplateListFilters = {
  /** Server defaults to true; pass false to see every version, not just each key's latest. */
  latestOnly?: boolean;
  category?: string;
  tag?: string;
  owner?: string;
  visibility?: TemplateVisibility;
  search?: string;
  templateKey?: string;
  publishedOnly?: boolean;
  includeDeleted?: boolean;
  deletedOnly?: boolean;
  sortBy?: 'created' | 'name';
  order?: 'asc' | 'desc';
  page?: number;
  perPage?: number;
  /** Super-admin only; same convention as fetchProcessModels/fetchProcessGroups. */
  tenantId?: string | null;
};

export function templatesPath(filters: TemplateListFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.latestOnly !== undefined) params.set('latest_only', String(filters.latestOnly));
  if (filters.category) params.set('category', filters.category);
  if (filters.tag) params.set('tag', filters.tag);
  if (filters.owner) params.set('owner', filters.owner);
  if (filters.visibility) params.set('visibility', filters.visibility);
  if (filters.search) params.set('search', filters.search);
  if (filters.templateKey) params.set('template_key', filters.templateKey);
  if (filters.publishedOnly !== undefined) params.set('published_only', String(filters.publishedOnly));
  if (filters.includeDeleted !== undefined) params.set('include_deleted', String(filters.includeDeleted));
  if (filters.deletedOnly !== undefined) params.set('deleted_only', String(filters.deletedOnly));
  if (filters.sortBy) params.set('sort_by', filters.sortBy);
  if (filters.order) params.set('order', filters.order);
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.perPage !== undefined) params.set('per_page', String(filters.perPage));
  if (filters.tenantId) params.set('tenantId', filters.tenantId);
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/templates?${qs}` : '/v1.0/m8flow/templates';
}

export async function fetchTemplates(filters: TemplateListFilters = {}): Promise<TemplateListResponse> {
  const response = await apiFetch(templatesPath(filters), { headers: { Accept: 'application/json' } });
  return (await response.json()) as TemplateListResponse;
}

/** Every version of a template key (`latest_only=false`). Soft-deleted rows stay excluded. */
export async function fetchTemplateVersions(
  templateKey: string,
  options: { tenantId?: string | null } = {},
): Promise<Template[]> {
  const response = await fetchTemplates({
    templateKey,
    latestOnly: false,
    perPage: 100,
    ...(options.tenantId ? { tenantId: options.tenantId } : {}),
  });
  return Array.isArray(response.results) ? response.results : [];
}

export function templatePath(id: number, options: { includeContents?: boolean; includeDeleted?: boolean } = {}): string {
  const params = new URLSearchParams();
  if (options.includeContents !== undefined) params.set('include_contents', String(options.includeContents));
  if (options.includeDeleted !== undefined) params.set('include_deleted', String(options.includeDeleted));
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/templates/${id}?${qs}` : `/v1.0/m8flow/templates/${id}`;
}

/** Designer route that opens one template file in DiagramCanvas. */
export function templateModelerFilePath(templateId: number, fileName: string): string {
  return `/templates/${templateId}/modeler/${encodeURIComponent(fileName)}`;
}

export function contentTypeForTemplateFileName(fileName: string): string {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.json')) return 'application/json';
  if (lower.endsWith('.md')) return 'text/markdown';
  return 'application/xml';
}

export async function fetchTemplate(
  id: number,
  options: { includeContents?: boolean; includeDeleted?: boolean } = {},
): Promise<Template> {
  const response = await apiFetch(templatePath(id, options), { headers: { Accept: 'application/json' } });
  return (await response.json()) as Template;
}

/**
 * Raw file content (BPMN/DMN/JSON Schema/Markdown text) for one of a
 * template's non-`bpmnContent` files — same "text, not JSON" pattern as
 * `fetchProcessModelFileContent`.
 */
export async function fetchTemplateFileContent(id: number, fileName: string): Promise<string> {
  const response = await apiFetch(`/v1.0/m8flow/templates/${id}/files/${encodeURIComponent(fileName)}`);
  return response.text();
}

/**
 * Updates one file's content. Per the backend's own draft-versioning
 * semantics: if `id` refers to a *published* template, this creates (or
 * reuses) a draft version and applies the edit there instead — the
 * returned `Template` reflects whichever version was actually written,
 * which may have a different `id` than the one passed in. Callers must
 * re-anchor on the returned `id`, not assume it matches the argument.
 */
export async function saveTemplateFileContent(
  id: number,
  fileName: string,
  content: string,
  contentType = 'application/octet-stream',
): Promise<Template> {
  const response = await apiFetch(`/v1.0/m8flow/templates/${id}/files/${encodeURIComponent(fileName)}`, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: content,
  });
  return (await response.json()) as Template;
}

export async function deleteTemplateFile(id: number, fileName: string): Promise<void> {
  await apiFetch(`/v1.0/m8flow/templates/${id}/files/${encodeURIComponent(fileName)}`, { method: 'DELETE' });
}

/** Metadata sent as `X-Template-*` headers, matching `_metadata_from_headers` on the backend. */
export type TemplateMetadataInput = {
  templateKey: string;
  name: string;
  description?: string;
  category?: string;
  tags?: string[];
  visibility?: TemplateVisibility;
  status?: string;
  version?: string;
  isPublished?: boolean;
};

function metadataHeaders(metadata: TemplateMetadataInput): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Template-Key': metadata.templateKey.trim(),
    'X-Template-Name': metadata.name.trim(),
  };
  if (metadata.description) headers['X-Template-Description'] = metadata.description;
  if (metadata.category) headers['X-Template-Category'] = metadata.category;
  if (metadata.tags && metadata.tags.length > 0) headers['X-Template-Tags'] = JSON.stringify(metadata.tags);
  if (metadata.visibility) headers['X-Template-Visibility'] = metadata.visibility;
  if (metadata.status) headers['X-Template-Status'] = metadata.status;
  if (metadata.version) headers['X-Template-Version'] = metadata.version;
  if (metadata.isPublished !== undefined) headers['X-Template-Is-Published'] = metadata.isPublished ? 'true' : 'false';
  return headers;
}

/** Creates a new single-file (BPMN) template. */
export async function createTemplate(bpmnXml: string, metadata: TemplateMetadataInput): Promise<Template> {
  const response = await apiFetch('/v1.0/m8flow/templates', {
    method: 'POST',
    headers: { ...metadataHeaders(metadata), 'Content-Type': 'application/xml' },
    body: bpmnXml,
  });
  return (await response.json()) as Template;
}

/** Creates a new multi-file template (e.g. BPMN + JSON Schema + Markdown docs). */
export async function createTemplateWithFiles(
  metadata: TemplateMetadataInput,
  files: { name: string; content: Blob }[],
): Promise<Template> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f.content, f.name));
  const response = await apiFetch('/v1.0/m8flow/templates', {
    method: 'POST',
    headers: metadataHeaders(metadata),
    body: form,
  });
  return (await response.json()) as Template;
}

/** Partial metadata update (no BPMN body) — JSON body, matching the backend's "legacy format" branch.
 * `isPublished` is sent as `is_published` so draft publish is a PUT `{ is_published: true }`. */
export async function updateTemplateMetadata(id: number, updates: Partial<TemplateMetadataInput>): Promise<Template> {
  const body: Record<string, unknown> = {};
  if (updates.name !== undefined) body.name = updates.name;
  if (updates.description !== undefined) body.description = updates.description;
  if (updates.category !== undefined) body.category = updates.category;
  if (updates.tags !== undefined) body.tags = updates.tags;
  if (updates.visibility !== undefined) body.visibility = updates.visibility;
  if (updates.status !== undefined) body.status = updates.status;
  if (updates.isPublished !== undefined) body.is_published = updates.isPublished;
  const response = await apiFetch(`/v1.0/m8flow/templates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return (await response.json()) as Template;
}

export async function deleteTemplate(id: number): Promise<void> {
  await apiFetch(`/v1.0/m8flow/templates/${id}`, { method: 'DELETE' });
}

export async function restoreTemplate(id: number): Promise<Template> {
  const response = await apiFetch(`/v1.0/m8flow/templates/${id}/restore`, { method: 'POST' });
  return (await response.json()) as Template;
}

export async function exportTemplate(id: number): Promise<Blob> {
  const response = await apiFetch(`/v1.0/m8flow/templates/${id}/export`);
  return response.blob();
}

export async function importTemplateZip(zipFile: File, metadata: TemplateMetadataInput): Promise<Template> {
  const form = new FormData();
  form.append('file', zipFile);
  const response = await apiFetch('/v1.0/m8flow/templates/import', {
    method: 'POST',
    headers: metadataHeaders(metadata),
    body: form,
  });
  return (await response.json()) as Template;
}

export type CreateProcessModelFromTemplateRequest = {
  processGroupId: string;
  processModelId: string;
  displayName: string;
  description?: string;
  /** Super-admin write binding (M8F-479); also sent as `?tenantId=`. */
  tenantId?: string | null;
};

export type ProcessModelTemplateInfo = {
  id: number;
  process_model_identifier: string;
  source_template_id: number;
  source_template_key: string;
  source_template_version: string;
  source_template_name: string;
  m8f_tenant_id: string;
  created_by: string;
  created_at_in_seconds: number;
  updated_at_in_seconds: number;
};

export type CreateProcessModelFromTemplateResponse = {
  process_model: Record<string, unknown>;
  template_info: ProcessModelTemplateInfo;
};

export async function createProcessModelFromTemplate(
  templateId: number,
  request: CreateProcessModelFromTemplateRequest,
): Promise<CreateProcessModelFromTemplateResponse> {
  const tenantId = request.tenantId?.trim() || null;
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const response = await apiFetch(
    `/v1.0/m8flow/templates/${templateId}/create-process-model${suffix}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        process_group_id: request.processGroupId,
        process_model_id: request.processModelId,
        display_name: request.displayName,
        description: request.description,
        ...(tenantId ? { m8f_tenant_id: tenantId } : {}),
      }),
    },
  );
  return (await response.json()) as CreateProcessModelFromTemplateResponse;
}

/** `modifiedProcessModelIdentifier` uses this app's `:`-separated form (see lib/processModelId.ts). */
export async function fetchProcessModelTemplateInfo(
  modifiedProcessModelIdentifier: string,
): Promise<ProcessModelTemplateInfo | null> {
  const response = await apiFetch(
    `/v1.0/m8flow/templates/process-models/${modifiedProcessModelIdentifier}/template-info`,
  );
  return (await response.json()) as ProcessModelTemplateInfo | null;
}

/** Direct download URL for a template file — for `<a href>`/`window.open`, not `fetch` (no auth header attached). */
export function templateFileDownloadUrl(id: number, fileName: string): string {
  return `${API_BASE_URL}/v1.0/m8flow/templates/${id}/files/${encodeURIComponent(fileName)}`;
}
