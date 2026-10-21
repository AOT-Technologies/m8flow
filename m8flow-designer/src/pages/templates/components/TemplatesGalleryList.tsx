import { useEffect, useRef, type KeyboardEvent } from 'react';
import type { ParseKeys } from 'i18next';
import { Download, FileText, RotateCcw, Trash2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

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

const VISIBILITY_OPTIONS: { value: VisibilityFilter; labelKey: ParseKeys }[] = [
  { value: 'ALL', labelKey: 'templates.visibility.all' },
  { value: 'PRIVATE', labelKey: 'templates.visibility.private' },
  { value: 'TENANT', labelKey: 'templates.visibility.tenant' },
  { value: 'PUBLIC', labelKey: 'templates.visibility.public' },
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
  const { t } = useTranslation();
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
  const resultCount = t('templates.gallery.resultCount', { count: totalCount });

  return (
    <>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[32px] font-semibold tracking-tight text-foreground">{t('templates.title')}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div
            className="flex items-center rounded-full bg-muted p-[3px]"
            role="group"
            aria-label={t('templates.gallery.modeGroupLabel')}
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
              {t('templates.gallery.modeActive')}
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
              {t('templates.gallery.modeDeleted')}
            </button>
          </div>
          {actor.canImportTemplates !== false || actor.isSuperAdmin ? <Button
            type="button"
            variant="pill-outline"
            size="pill"
            onClick={onImportClick}
            disabled={isSuperAdmin || !onImportClick}
            title={isSuperAdmin ? t('templates.notAvailableToSuperAdmin') : undefined}
            className="gap-1.5"
          >
            <Upload className="size-3.5" strokeWidth={2.2} />
            {t('templates.import')}
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
            placeholder={t('templates.gallery.search')}
            aria-label={t('templates.gallery.search')}
            className="max-w-[420px] min-w-0 flex-1"
          />

          <SortDropdown
            label={t('templates.visibility.label')}
            options={VISIBILITY_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }))}
            value={visibility}
            onChange={(value) => onVisibilityChange(value as VisibilityFilter)}
            className="min-w-0"
          />

          <button
            type="button"
            onClick={onToggleOrder}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-[13px] font-medium text-foreground"
            aria-label={t(order === 'desc' ? 'templates.gallery.sortAriaNewest' : 'templates.gallery.sortAriaOldest')}
          >
            {t('templates.gallery.sortUpdated', { arrow: order === 'desc' ? '↓' : '↑' })}
          </button>

          <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
            {loading ? t('common.loading') : resultCount}
          </div>
        </div>

        {error ? (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="py-8 text-sm text-muted-foreground" aria-busy="true">
            {t('templates.gallery.loadingTemplates')}
          </p>
        ) : null}

        {isEmpty ? (
          <EmptyState
            title={t(galleryMode === 'deleted' ? 'templates.gallery.emptyDeletedTitle' : 'templates.gallery.emptyTitle')}
            description={
              search.trim() || visibility !== 'ALL'
                ? t('templates.gallery.emptyFiltered')
                : galleryMode === 'deleted'
                  ? t('templates.gallery.emptyDeletedDescription')
                  : t('templates.gallery.emptyDescription')
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

/** Tags minus any that repeat the category or each other (case-insensitive) —
 * sample templates are seeded with category "Sample" and tag "sample". */
function uniqueTags(template: Template): string[] {
  const seen = new Set(template.category ? [template.category.toLowerCase()] : []);
  return (template.tags ?? []).filter((tag) => {
    const key = tag.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
  const { t } = useTranslation();
  const deletedMode = galleryMode === 'deleted';
  const useDisabled = deletedMode || !template.isPublished || !canUseTemplate;
  const useTitle = !canUseTemplate
    ? t('templates.card.useNoPermission')
    : deletedMode
      ? t('templates.card.useDeleted')
      : !template.isPublished
        ? t('templates.card.useUnpublished')
        : undefined;
  const canDeleteTemplates = actor.canDeleteTemplates !== false || actor.isSuperAdmin;
  const canRestoreTemplates = actor.canRestoreTemplates !== false || actor.isSuperAdmin;
  const canDelete = canDeleteGalleryTemplate(template, actor);
  const deleteTitle = canDelete ? t('templates.card.deleteTemplate') : deleteDisabledReason(template, actor);
  const canRestore = canRestoreGalleryTemplate(actor);
  const restoreTitle = canRestore
    ? t('templates.card.restoreTemplate')
    : actor.isSuperAdmin
      ? t('templates.notAvailableToSuperAdmin')
      : t('templates.permissions.restore');

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
          {actor.isSuperAdmin ? (
            <div className="mt-0.5 line-clamp-1 text-[12px] text-muted-foreground">
              {t('templates.card.tenant', { tenant: template.tenant?.name || template.tenantId || '—' })}
            </div>
          ) : null}
        </div>
        <Pill tone={template.isPublished ? 'success' : 'muted'} dot={false} className="shrink-0">
          {t(template.isPublished ? 'common.modelStatus.published' : 'common.modelStatus.draft')}
        </Pill>
      </div>

      {template.description ? (
        <p className="line-clamp-2 text-[13px] text-muted-foreground">{template.description}</p>
      ) : (
        <p className="text-[13px] text-muted-foreground italic">{t('templates.card.noDescription')}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <Pill dot={false}>{t(`templates.visibilityBadge.${template.visibility}`, { defaultValue: template.visibility })}</Pill>
        {template.category ? <Pill dot={false}>{template.category}</Pill> : null}
        {uniqueTags(template).slice(0, 2).map((tag) => (
          <Pill key={tag} dot={false}>
            {tag}
          </Pill>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3 text-[12px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <FileText className="size-3.5" strokeWidth={1.8} />
          {t('templates.card.fileCount', { count: template.files.length })}
        </span>
        <span>{t('templates.card.updated', { time: formatRelativeTime(template.updatedAt) })}</span>
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
          {t('templates.card.open')}
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
            {t('templates.card.useTemplate')}
          </button>
        )}
        <span className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onExport();
            }}
            title={t('templates.card.exportAsZip')}
            aria-label={t('templates.card.exportTemplate')}
            className="flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Download className="size-3.5" strokeWidth={1.8} />
          </button>
          {deletedMode ? (
            canRestoreTemplates ? (
            <button
              type="button"
              aria-disabled={!canRestore}
              title={restoreTitle}
              aria-label={t('templates.card.restoreTemplate')}
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
            canDeleteTemplates ? <button
              type="button"
              aria-disabled={!canDelete}
              title={deleteTitle}
              aria-label={t('templates.card.deleteTemplate')}
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
