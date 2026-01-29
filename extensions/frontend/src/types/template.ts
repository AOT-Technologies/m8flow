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
  createdAt: string;
  createdBy: string;
  updatedAt: string | null;
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
