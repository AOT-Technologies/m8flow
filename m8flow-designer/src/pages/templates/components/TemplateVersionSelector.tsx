import type { Template } from '@/lib/templatesApi';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type TemplateVersionSelectorProps = {
  current: Template;
  versions: Template[];
  onSelect: (templateId: number) => void;
  loading?: boolean;
};

function versionSortKey(version: string): number {
  const trimmed = (version || '').trim();
  if (/^v\d+$/i.test(trimmed)) {
    return Number.parseInt(trimmed.slice(1), 10);
  }
  return 0;
}

export function mergeTemplateVersions(versions: Template[], current: Template): Template[] {
  const byId = new Map<number, Template>();
  for (const row of versions) {
    byId.set(row.id, row);
  }
  byId.set(current.id, current);
  return [...byId.values()].sort((a, b) => {
    const byVersion = versionSortKey(a.version) - versionSortKey(b.version);
    return byVersion !== 0 ? byVersion : a.id - b.id;
  });
}

function optionLabel(version: Template, currentId: number): string {
  const status = version.isPublished ? 'Published' : 'Draft';
  const current = version.id === currentId ? ' · current' : '';
  return `${version.version} · ${status}${current}`;
}

/**
 * Version switcher for template detail. Hidden when the key has only one
 * version. Changing the value navigates to that version's id (Templates
 * to 100%, ticket 08).
 */
export function TemplateVersionSelector({
  current,
  versions,
  onSelect,
  loading = false,
}: TemplateVersionSelectorProps) {
  const merged = mergeTemplateVersions(versions, current);
  if (merged.length <= 1) return null;

  return (
    <div className="border-b border-border px-6 py-3">
      <div className="flex max-w-xs flex-col gap-1.5">
        <span aria-hidden className="text-xs font-medium text-muted-foreground">All versions</span>
        <Select
          value={String(current.id)}
          disabled={loading}
          onValueChange={(value) => {
            const nextId = Number(value);
            if (Number.isFinite(nextId) && nextId !== current.id) {
              onSelect(nextId);
            }
          }}
        >
          <SelectTrigger aria-label="All versions">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {merged.map((version) => (
              <SelectItem key={version.id} value={String(version.id)}>
                {optionLabel(version, current.id)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
