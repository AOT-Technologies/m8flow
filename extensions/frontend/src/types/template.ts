export type TemplateVisibility = 'PRIVATE' | 'TENANT' | 'PUBLIC';

export type TemplateFileType = 'bpmn' | 'json' | 'dmn' | 'md';

export interface TemplateFile {
  fileType: TemplateFileType;
  fileName: string;
}

export interface Template {
  id: number;
  templateKey: string;
  version: string;
  name: string;
  description: string | null;
  tags: string[] | null;
  category: string | null;
  tenantId: string | null;
  visibility: TemplateVisibility;
  files: TemplateFile[];
  bpmnContent?: string; // Included in GET when include_contents true
  isPublished: boolean;
  status: string | null;
  /** Epoch seconds for display (Spiff-style). */
  createdAtInSeconds: number;
  createdBy: string;
  /** Epoch seconds for display (Spiff-style). */
  updatedAtInSeconds: number;
  modifiedBy: string;
}

export interface TemplateFilters {
  search?: string;
  category?: string;
  tag?: string;
  visibility?: TemplateVisibility;
  owner?: string;
  latest_only?: boolean;
  page?: number;
  per_page?: number;
}

/** Metadata for creating a template via POST (maps to X-Template-* headers). */
export interface CreateTemplateMetadata {
  template_key: string;
  name: string;
  description?: string;
  category?: string;
  tags?: string[] | string;
  visibility?: TemplateVisibility;
  status?: string;
  version?: string;
  is_published?: boolean;
}

/** Request body for creating a process model from a template. */
export interface CreateProcessModelFromTemplateRequest {
  process_group_id: string;
  process_model_id: string;
  display_name: string;
  description?: string;
}

/** Template provenance info for a process model. */
export interface ProcessModelTemplateInfo {
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
}

/** Response from creating a process model from a template. */
export interface CreateProcessModelFromTemplateResponse {
  process_model: Record<string, unknown>;
  template_info: ProcessModelTemplateInfo;
}
