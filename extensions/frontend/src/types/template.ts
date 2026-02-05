export type TemplateVisibility = 'PRIVATE' | 'TENANT' | 'PUBLIC';

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
  bpmnObjectKey: string;
  bpmnContent?: string; // Included in GET responses
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
