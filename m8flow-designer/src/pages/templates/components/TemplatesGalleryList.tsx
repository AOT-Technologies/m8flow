import { useEffect, useRef, type KeyboardEvent } from 'react';
import { Download, FileText, Plus, RotateCcw, Trash2, Upload } from 'lucide-react';

import type { Template, TemplateVisibility } from '@/lib/templatesApi';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { SortDropdown } from '@/components/library/sort-dropdown/SortDropdown';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';
import {
  canDeleteGalleryTemplate,
  canRestoreGalleryTemplate,
  deleteDisabledReason,
  type TemplateGalleryActor,
  type TemplateGalleryMode,
} from './templateGalleryPermissions';

export type { TemplateGalleryMode };
export type VisibilityFilter = TemplateVisibility | 'ALL';

export type TemplatesGalleryListProps = {
  templates: Template[];
  loading?: boolean;
  error?: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  visibility: VisibilityFilter;
  onVisibilityChange: (value: VisibilityFilter) => void;
  order: 'asc' | 'desc';
  onToggleOrder: () => void;
  page: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (page: number) => void;
  onOpenTemplate?: (template: Template) => void;
  /** Opens the create-process-model-from-template dialog. Only enabled for
   * published templates when the caller isn't a super-admin (see this
   * component's own doc comment). */
  onUseTemplate?: (template: Template) => void;
  onExportTemplate?: (template: Template) => void;
  onDeleteTemplate?: (template: Template) => void;
  onRestoreTemplate?: (template: Template) => void;
  onImportClick?: () => void;
  galleryMode: TemplateGalleryMode;
  onGalleryModeChange: (mode: TemplateGalleryMode) => void;
  actor: TemplateGalleryActor;
  /**
   * Gates Import (and other template-mutating actions): template CRUD remains
   * SA-blocked server-side. "Use template" is gated separately via
   * `canUseTemplate` (M8F-479 allows SA create-from-template with a tenant).
   */
  isSuperAdmin?: boolean;
  /**
   * When false (e.g. super-admin on All Tenants), Use template stays disabled.
   * Defaults true so callers that omit it keep prior non-SA behavior.
   */
  canUseTemplate?: boolean;
};

const VISIBILITY_OPTIONS: { value: VisibilityFilter; label: string }[] = [
  { value: 'ALL', label: 'All visibility' },
  { value: 'PRIVATE', label: 'Private' },
  { value: 'TENANT', label: 'Tenant' },
  { value: 'PUBLIC', label: 'Public' },
];

/**
 * Templates gallery — search/filter/sort/paginate over
 * `GET /v1.0/m8flow/templates`, matching this app's own Processes-list
 * conventions (`ProcessesModelsList.tsx`) rather than porting
 * `m8flow-frontend`'s Carbon-based `TemplateGalleryPage`. Presentational:
 * the parent (`TemplatesPage`) owns fetching and filter state.
 */
export function TemplatesGalleryList({
  templates,
  loading = false,
  error = null,
  search,
  onSearchChange,
  visibility,
  onVisibilityChange,
  order,
  onToggleOrder,
  page,
  pageSize,
  totalCount,
  onPageChange,
  onOpenTemplate,
  onUseTemplate,
  onExportTemplate,
  onDeleteTemplate,
  onRestoreTemplate,
  onImportClick,
  galleryMode,
  onGalleryModeChange,
  actor,
  isSuperAdmin = false,
  canUseTemplate = true,
}: TemplatesGalleryListProps) {
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      onSearchChange('');
      searchRef.current?.blur();
    }
  }

  const isEmpty = !loading && !error && templates.length === 0;
  const resultCount = `${totalCount} template${totalCount === 1 ? '' : 's'}`;

  return (
    <>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[32px] font-semibold tracking-tight text-foreground">Templates</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div
            className="flex items-center rounded-full bg-muted p-[3px]"
            role="group"
            aria-label="Template mode"
          >
            <button
              type="button"
              aria-pressed={galleryMode === 'active'}
              onClick={() => onGalleryModeChange('active')}
              className={cn(
                'rounded-full px-4 py-2 text-[12.5px] font-semibold',
                galleryMode === 'active'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground',
              )}
            >
              Active
            </button>
            <button
              type="button"
              aria-pressed={galleryMode === 'deleted'}
              onClick={() => onGalleryModeChange('deleted')}
              className={cn(
                'rounded-full px-4 py-2 text-[12.5px] font-semibold',
                galleryMode === 'deleted'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground',
              )}
            >
              Deleted
            </button>
          </div>
          {actor.canManageTemplates !== false || actor.isSuperAdmin ? <Button
            type="button"
            variant="pill-outline"
            size="pill"
            onClick={onImportClick}
            disabled={isSuperAdmin || !onImportClick}
            title={isSuperAdmin ? 'Not available to super-admin' : undefined}
            className="gap-1.5"
          >
            <Upload className="size-3.5" strokeWidth={2.2} />
            Import
          </Button> : null}
          {/* Blank-template creation deliberately out of scope for this
              ticket (no starter-BPMN precedent exists elsewhere in this
              app — "New process model" is the same kind of still-inert
              chrome on ProcessesModelsList). */}
          {actor.canManageTemplates !== false || actor.isSuperAdmin ? <Button
            type="button"
            variant="pill"
            size="pill"
            disabled
            title="Not yet available — use Import or create a template from an existing process model"
            className="gap-2"
          >
            <Plus className="size-[15px]" strokeWidth={2.2} />
            New template
          </Button> : null}
        </div>
      </div>

      <div className="pb-14">
        <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
          <SearchBar
            ref={searchRef}
            type="search"
            value={search}
            onChange={onSearchChange}
            onKeyDown={onSearchKeyDown}
            placeholder="Search templates"
            aria-label="Search templates"
            className="max-w-[420px] min-w-0 flex-1"
          />

          <SortDropdown
            label="Visibility"
            options={VISIBILITY_OPTIONS}
            value={visibility}
            onChange={(value) => onVisibilityChange(value as VisibilityFilter)}
            className="min-w-0"
          />

          <button
            type="button"
            onClick={onToggleOrder}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-[13px] font-medium text-foreground"
            aria-label={`Sort by last updated, currently ${order === 'desc' ? 'newest first' : 'oldest first'}`}
          >
            Sort: updated {order === 'desc' ? '↓' : '↑'}
          </button>

          <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
            {loading ? 'Loading…' : resultCount}
          </div>
        </div>

        {error ? (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="py-8 text-sm text-muted-foreground" aria-busy="true">
            Loading templates…
          </p>
        ) : null}

        {isEmpty ? (
          <EmptyState
            title={galleryMode === 'deleted' ? 'No deleted templates' : 'No templates found'}
            description={
              search.trim() || visibility !== 'ALL'
                ? 'Try a different search or clear the filters.'
                : galleryMode === 'deleted'
                  ? 'No soft-deleted templates for this tenant.'
                  : 'No templates are available for this tenant yet.'
            }
          />
        ) : null}

        {!loading && templates.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {templates.map((template) => (
              <TemplateCard
                key={template.id}
                template={template}
                galleryMode={galleryMode}
                actor={actor}
                canUseTemplate={canUseTemplate}
                onOpen={() => onOpenTemplate?.(template)}
                onUse={() => onUseTemplate?.(template)}
                onExport={() => onExportTemplate?.(template)}
                onDelete={() => onDeleteTemplate?.(template)}
                onRestore={() => onRestoreTemplate?.(template)}
              />
            ))}
          </div>
        ) : null}

        {!loading && !isEmpty ? (
          <div className="mt-4">
            <Pagination page={page} onPageChange={onPageChange} totalItems={totalCount} pageSize={pageSize} />
          </div>
        ) : null}
      </div>
    </>
  );
}

function TemplateCard({
  template,
  galleryMode,
  actor,
  canUseTemplate,
  onOpen,
  onUse,
  onExport,
  onDelete,
  onRestore,
}: {
  template: Template;
  galleryMode: TemplateGalleryMode;
  actor: TemplateGalleryActor;
  canUseTemplate: boolean;
  onOpen: () => void;
  onUse: () => void;
  onExport: () => void;
  onDelete: () => void;
  onRestore: () => void;
}) {
  const deletedMode = galleryMode === 'deleted';
  const useDisabled = deletedMode || !template.isPublished || !canUseTemplate;
  const useTitle = !canUseTemplate
    ? 'Creating a process model requires permission and a selected tenant'
    : deletedMode
      ? 'Restore this template before creating a process model'
      : !template.isPublished
        ? 'Only published templates can be used to create a process model'
        : undefined;
  const canManageTemplates = actor.canManageTemplates !== false || actor.isSuperAdmin;
  const canDelete = canDeleteGalleryTemplate(template, actor);
  const deleteTitle = canDelete ? 'Delete template' : deleteDisabledReason(template, actor);
  const canRestore = canRestoreGalleryTemplate(actor);
  const restoreTitle = canRestore
    ? 'Restore template'
    : actor.isSuperAdmin
      ? 'Not available to super-admin'
      : 'Insufficient permissions to restore deleted templates.';

  return (
    <Card
      variant="bordered"
      role={deletedMode ? undefined : 'button'}
      tabIndex={deletedMode ? undefined : 0}
      onClick={deletedMode ? undefined : onOpen}
      onKeyDown={
        deletedMode
          ? undefined
          : (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpen();
              }
            }
      }
      className={cn('flex flex-col gap-3 p-5', deletedMode ? '' : 'cursor-pointer')}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="line-clamp-1 text-[14.5px] font-semibold text-foreground">{template.name}</div>
          <div className="mt-0.5 font-mono text-[11.5px] text-muted-foreground">
            {template.templateKey} · v{template.version}
          </div>
        </div>
        <Pill tone={template.isPublished ? 'success' : 'muted'} dot={false} className="shrink-0">
          {template.isPublished ? 'Published' : 'Draft'}
        </Pill>
      </div>

      {template.description ? (
        <p className="line-clamp-2 text-[13px] text-muted-foreground">{template.description}</p>
      ) : (
        <p className="text-[13px] text-muted-foreground italic">No description</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <Pill dot={false}>{template.visibility}</Pill>
        {template.category ? <Pill dot={false}>{template.category}</Pill> : null}
        {(template.tags ?? []).slice(0, 2).map((tag) => (
          <Pill key={tag} dot={false}>
            {tag}
          </Pill>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3 text-[12px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <FileText className="size-3.5" strokeWidth={1.8} />
          {template.files.length} file{template.files.length === 1 ? '' : 's'}
        </span>
        <span>Updated {formatRelativeTime(template.updatedAtInSeconds)}</span>
      </div>

      <div
        className="flex flex-wrap items-center gap-2"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Button
          type="button"
          variant="pill-outline"
          size="pill"
          onClick={onOpen}
          disabled={deletedMode}
          className="px-3.5 py-1.5 text-[11.5px]"
        >
          Open
        </Button>
        {deletedMode || (!canUseTemplate && !actor.isSuperAdmin) ? null : (
          <button
            type="button"
            aria-disabled={useDisabled}
            title={useTitle}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (!useDisabled) onUse();
            }}
            disabled={useDisabled}
            className={cn(
              'inline-flex items-center rounded-full px-3.5 py-1.5 text-[11.5px] font-semibold tracking-[0.04em] uppercase select-none',
              'border border-border',
              useDisabled ? 'cursor-default text-muted-foreground' : 'cursor-pointer text-foreground hover:bg-muted',
            )}
          >
            Use template
          </button>
        )}
        <span className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onExport();
            }}
            title="Export as zip"
            aria-label="Export template"
            className="flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Download className="size-3.5" strokeWidth={1.8} />
          </button>
          {deletedMode ? (
            canManageTemplates ? (
            <button
              type="button"
              aria-disabled={!canRestore}
              title={restoreTitle}
              aria-label="Restore template"
              onClick={(e) => {
                e.stopPropagation();
                if (canRestore) onRestore();
              }}
              className={cn(
                'flex size-7 items-center justify-center rounded-full',
                canRestore
                  ? 'cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground'
                  : 'cursor-default text-muted-foreground/50',
              )}
            >
              <RotateCcw className="size-3.5" strokeWidth={1.8} />
            </button>
            ) : null
          ) : (
            canManageTemplates ? <button
              type="button"
              aria-disabled={!canDelete}
              title={deleteTitle}
              aria-label="Delete template"
              onClick={(e) => {
                e.stopPropagation();
                if (canDelete) onDelete();
              }}
              className={cn(
                'flex size-7 items-center justify-center rounded-full',
                canDelete
                  ? 'cursor-pointer text-muted-foreground hover:bg-destructive/10 hover:text-destructive'
                  : 'cursor-default text-muted-foreground/50',
              )}
            >
              <Trash2 className="size-3.5" strokeWidth={1.8} />
            </button> : null
          )}
        </span>
      </div>
    </Card>
  );
}
