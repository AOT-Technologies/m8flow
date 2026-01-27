export type TemplateVisibility = 'PRIVATE' | 'TENANT' | 'PUBLIC';

export interface Template {
  id: number;
  template_key: string;
  version: string;
  name: string;
  description: string | null;
  tags: string[] | null;
  category: string | null;
  tenant_id: string | null;
  visibility: TemplateVisibility;
  bpmn_object_key: string;
  bpmn_content?: string; // Included in GET responses
  is_published: boolean;
  status: string | null;
  created_at: string;
  created_by: string;
  updated_at: string | null;
  updated_by: string;
}

export interface TemplateFilters {
  search?: string;
  category?: string;
  tag?: string;
  visibility?: TemplateVisibility;
  owner?: string;
  latest_only?: boolean;
}
