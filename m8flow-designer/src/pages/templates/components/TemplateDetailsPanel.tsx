import { useEffect, useState } from 'react';

import { ApiError } from '@/lib/api';
import { formatRelativeTime } from '@/lib/relativeTime';
import {
  updateTemplateMetadata,
  type Template,
  type TemplateVisibility,
} from '@/lib/templatesApi';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export type TemplateDetailsPanelProps = {
  template: Template;
  /** PUT /m8flow/templates (visibility/publish): not super-admin. */
  canManage: boolean;
  /**
   * Create-from-template (M8F-479). Super-admin may create when a concrete
   * tenant is selected; template metadata mutate stays behind `canManage`.
   */
  canCreateProcessModel?: boolean;
  onTemplateChange: (template: Template) => void;
  onCreateProcessModel: () => void;
};

const VISIBILITY_OPTIONS: TemplateVisibility[] = ['PRIVATE', 'TENANT', 'PUBLIC'];

/**
 * Publish and draft-visibility chrome for template detail / template
 * modeler. Draft + canManage: visibility select + Save, and Publish.
 * Published: read-only visibility chip, no unpublish. Create process
 * model stays published-only.
 */
export function TemplateDetailsPanel({
  template,
  canManage,
  canCreateProcessModel = canManage,
  onTemplateChange,
  onCreateProcessModel,
}: TemplateDetailsPanelProps) {
  const [pendingVisibility, setPendingVisibility] = useState<TemplateVisibility>(template.visibility);
  const [savingVisibility, setSavingVisibility] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setPendingVisibility(template.visibility);
    setError(null);
  }, [template.id, template.visibility]);

  const visibilityDirty = pendingVisibility !== template.visibility;
  const canEditDraft = canManage && !template.isPublished;
  const createDisabled = !template.isPublished;
  const createTitle = createDisabled
    ? 'Process models can only be created from a published template version.'
    : undefined;

  async function handleSaveVisibility() {
    if (!visibilityDirty) return;
    setSavingVisibility(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateTemplateMetadata(template.id, { visibility: pendingVisibility });
      onTemplateChange(updated);
      setNotice('Visibility updated.');
    } catch (err) {
      const fromServer = err instanceof ApiError ? err.serverMessage : undefined;
      setError(fromServer || (err instanceof Error ? err.message : 'Failed to update visibility'));
    } finally {
      setSavingVisibility(false);
    }
  }

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateTemplateMetadata(template.id, { isPublished: true });
      onTemplateChange(updated);
      setNotice('Template published.');
    } catch (err) {
      const fromServer = err instanceof ApiError ? err.serverMessage : undefined;
      setError(fromServer || (err instanceof Error ? err.message : 'Failed to publish template'));
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section className="border-b border-border px-6 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-[18px] font-semibold tracking-tight text-foreground">{template.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge variant="outline">Version {template.version}</Badge>
            {template.category ? <Badge variant="outline">{template.category}</Badge> : null}
            {canEditDraft ? (
              <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <span className="sr-only">Visibility</span>
                <select
                  aria-label="Visibility"
                  value={pendingVisibility}
                  onChange={(e) => setPendingVisibility(e.target.value as TemplateVisibility)}
                  disabled={savingVisibility || publishing}
                  className="h-7 rounded-lg border border-input bg-transparent px-2 text-[12.5px] text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {VISIBILITY_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <Badge variant="secondary">{template.visibility}</Badge>
            )}
            {template.status ? <Badge variant="outline">{template.status}</Badge> : null}
            {template.createdBy ? <Badge variant="ghost">Created by {template.createdBy}</Badge> : null}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Created {formatRelativeTime(template.createdAtInSeconds)} · Updated{' '}
            {formatRelativeTime(template.updatedAtInSeconds)}
          </p>
          {template.description ? (
            <p className="mt-2 max-w-[820px] text-[13.5px] leading-normal text-muted-foreground">
              {template.description}
            </p>
          ) : null}
          {template.isPublished ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Saving diagram changes creates a new draft version.
            </p>
          ) : null}
        </div>

        {canManage || canCreateProcessModel ? (
          <div className="flex flex-none flex-wrap items-center gap-2">
            {canManage && canEditDraft && visibilityDirty ? (
              <Button
                type="button"
                variant="pill-outline"
                size="pill"
                onClick={() => void handleSaveVisibility()}
                disabled={savingVisibility || publishing}
              >
                {savingVisibility ? 'Saving…' : 'Save visibility'}
              </Button>
            ) : null}
            {canCreateProcessModel ? (
              <Button
                type="button"
                variant="pill-outline"
                size="pill"
                onClick={onCreateProcessModel}
                disabled={createDisabled}
                title={createTitle}
              >
                Create process model
              </Button>
            ) : null}
            {canManage && canEditDraft ? (
              <Button
                type="button"
                variant="pill-info"
                size="pill"
                onClick={() => void handlePublish()}
                disabled={publishing || savingVisibility}
              >
                {publishing ? 'Publishing…' : 'Publish'}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {error ? (
        <p className="mt-3 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mt-3 text-sm text-muted-foreground" role="status">
          {notice}
        </p>
      ) : null}
    </section>
  );
}
