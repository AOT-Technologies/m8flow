import { CodeXml, Download, History, Play, Plus, Send, Star, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import type { ProcessModelStatus } from '@/lib/api';
import { SaveButton } from './SaveButton';
import { SavedStatusPill, type SaveStatus } from './SavedStatusPill';

export type ModelerSavePhase = 'saved' | 'dirty' | 'saving' | 'error';

export type ModelerFileToolbarProps = {
  savePhase: ModelerSavePhase;
  fileLoaded: boolean;
  canCreateFile: boolean;
  canDeleteFile: boolean;
  canSetPrimary: boolean;
  isPrimary: boolean;
  isBpmn: boolean;
  isDiagram: boolean;
  onSave: () => void;
  onDownload: () => void;
  onNewFile?: () => void;
  onDelete?: () => void;
  onSetPrimary?: () => void;
  onViewXml?: () => void;
  /** Model lifecycle status; unknown until the detail fetch resolves. */
  status?: ProcessModelStatus | null;
  /** Saved working copy differs from the live version (published/paused). */
  hasUnpublishedChanges?: boolean;
  /** Publishes, resumes, or publishes changes. Absent without the publish permission. */
  onPublish?: () => void;
  /** Opens the version history. Absent without the history permission. */
  onHistory?: () => void;
  /** Starts an instance. Absent without the start permission. */
  onStart?: () => void;
  lifecycleBusy?: 'publishing' | 'starting' | null;
};

// Same height/shape as the other toolbar buttons, filled to read as primary.
const primaryAction =
  'gap-1.5 border-transparent bg-nav-active font-semibold hover:bg-nav-active/80 hover:text-foreground';

function pillStatus(phase: ModelerSavePhase): SaveStatus {
  if (phase === 'saving') return 'saving';
  if (phase === 'error') return 'error';
  return 'saved';
}

/** File actions on the process-modeler header — Save/Download plus the
 * old-canvas chrome (new file, delete non-primary, set primary, view XML).
 * The lifecycle action is the primary button: Publish (Resume when paused)
 * for an unpublished model, Start process for a published one, plus Publish
 * changes while saved edits are not live yet. Publishing needs a saved file,
 * so it is disabled while there are unsaved changes; Start runs the live
 * version, so unsaved edits don't affect it. Save-as-template stays off this bar. */
export function ModelerFileToolbar({
  savePhase,
  fileLoaded,
  canCreateFile,
  canDeleteFile,
  canSetPrimary: canChangePrimary,
  isPrimary,
  isBpmn,
  isDiagram,
  onSave,
  onDownload,
  onNewFile,
  onDelete,
  onSetPrimary,
  onViewXml,
  status,
  hasUnpublishedChanges = false,
  onPublish,
  onHistory,
  onStart,
  lifecycleBusy = null,
}: ModelerFileToolbarProps) {
  const { t } = useTranslation();
  const dirty = savePhase === 'dirty' || savePhase === 'saving';
  const canDelete = canDeleteFile && !isPrimary && Boolean(onDelete);
  const canPrimary = canChangePrimary && isBpmn && !isPrimary && Boolean(onSetPrimary);
  const showPublishChanges = status === 'published' && hasUnpublishedChanges && Boolean(onPublish);
  const showPublish = Boolean(status) && status !== 'published' && Boolean(onPublish);
  const showStart = status === 'published' && Boolean(onStart);

  return (
    <div className="flex flex-none flex-wrap items-center justify-end gap-2">
      {savePhase === 'dirty' ? (
        <SaveButton onClick={onSave} />
      ) : (
        <SavedStatusPill status={pillStatus(savePhase)} />
      )}
      {canCreateFile && onNewFile ? (
        <Button type="button" variant="outline" size="sm" onClick={onNewFile} className="gap-1.5">
          <Plus className="size-3.5" strokeWidth={2.2} />
          {t('modeler.toolbar.newFile')}
        </Button>
      ) : null}
      {canPrimary ? (
        <Button type="button" variant="outline" size="sm" onClick={onSetPrimary} className="gap-1.5">
          <Star className="size-3.5" strokeWidth={2.2} />
          {t('modeler.toolbar.setAsPrimary')}
        </Button>
      ) : null}
      {isDiagram && onViewXml ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onViewXml}
          disabled={!fileLoaded}
          className="gap-1.5"
        >
          <CodeXml className="size-3.5" strokeWidth={2.2} />
          {t('modeler.toolbar.viewXml')}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onDownload}
        disabled={!fileLoaded}
        className="gap-1.5"
      >
        <Download className="size-3.5" strokeWidth={2.2} />
        {t('modeler.toolbar.download')}
      </Button>
      {canDelete ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onDelete}
          className="gap-1.5 text-destructive hover:text-destructive"
        >
          <Trash2 className="size-3.5" strokeWidth={2.2} />
          {t('common.delete')}
        </Button>
      ) : null}
      {onHistory ? (
        <Button type="button" variant="outline" size="sm" onClick={onHistory} className="gap-1.5">
          <History className="size-3.5" strokeWidth={2.2} />
          {t('modeler.toolbar.history')}
        </Button>
      ) : null}
      {showPublishChanges || showPublish || showStart ? (
        // File actions | lifecycle actions: the divider keeps the primary
        // buttons from running into the file buttons.
        <span className="mx-1 h-6 w-px bg-border" aria-hidden data-testid="toolbar-divider" />
      ) : null}
      {showPublishChanges ? (
        <span title={dirty ? t('modeler.toolbar.saveBeforePublishing') : undefined}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onPublish}
            disabled={dirty || lifecycleBusy !== null}
            className={primaryAction}
          >
            <Send className="size-3.5" strokeWidth={2.2} />
            {lifecycleBusy === 'publishing' ? t('modeler.toolbar.publishing') : t('modeler.toolbar.publishChanges')}
          </Button>
        </span>
      ) : null}
      {showPublish ? (
        <span title={dirty ? t('modeler.toolbar.saveBeforePublishing') : undefined}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onPublish}
            disabled={dirty || lifecycleBusy !== null}
            className={primaryAction}
          >
            <Send className="size-3.5" strokeWidth={2.2} />
            {lifecycleBusy === 'publishing'
              ? status === 'paused'
                ? t('modeler.toolbar.resuming')
                : t('modeler.toolbar.publishing')
              : status === 'paused'
                ? t('modeler.toolbar.resume')
                : t('modeler.toolbar.publish')}
          </Button>
        </span>
      ) : null}
      {showStart ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onStart}
          disabled={lifecycleBusy !== null}
          className={primaryAction}
        >
          <Play className="size-3.5" strokeWidth={2.2} />
          {lifecycleBusy === 'starting' ? t('modeler.toolbar.starting') : t('modeler.toolbar.startProcess')}
        </Button>
      ) : null}
    </div>
  );
}
