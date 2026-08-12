/**
 * ProcessGroup → ProcessGroupLite, preserving API tenant fields for chips.
 */
import type { ProcessGroup, ProcessGroupLite } from '../../interfaces';

export type ProcessGroupLiteWithTenant = ProcessGroupLite & {
  tenantId?: string;
  tenantName?: string;
};

export const processGroupToLite = (
  group: ProcessGroup,
): ProcessGroupLiteWithTenant => {
  const g = group as ProcessGroup & { tenantId?: string; tenantName?: string };
  return {
    id: group.id,
    display_name: group.display_name,
    description: group.description || '',
    process_models: group.process_models,
    process_groups: group.process_groups
      ? group.process_groups.map(processGroupToLite)
      : undefined,
    tenantId: g.tenantId,
    tenantName: g.tenantName,
  };
};
