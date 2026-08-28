type ProcessTreeItem = {
  id?: string;
  tenantName?: string;
  process_groups?: ProcessTreeItem[];
  process_models?: ProcessTreeItem[];
};

const tenantLabelsById = new Map<string, string>();

function normalizedString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed || undefined;
}

function registerItem(item: ProcessTreeItem): void {
  const id = normalizedString(item.id);
  const tenantName = normalizedString(item.tenantName);
  if (id && tenantName) {
    tenantLabelsById.set(id, tenantName);
  }
  item.process_groups?.forEach(registerItem);
  item.process_models?.forEach(registerItem);
}

export function registerProcessTenantLabels(items: unknown): void {
  tenantLabelsById.clear();
  if (!Array.isArray(items)) {
    return;
  }
  items.forEach((item) => {
    if (item && typeof item === 'object') {
      registerItem(item as ProcessTreeItem);
    }
  });
}

export function getProcessTenantLabel(id: string | null | undefined): string | undefined {
  if (!id) {
    return undefined;
  }
  return tenantLabelsById.get(id);
}

export function clearProcessTenantLabels(): void {
  tenantLabelsById.clear();
}
