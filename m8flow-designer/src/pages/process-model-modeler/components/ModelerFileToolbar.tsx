import { CodeXml, Download, Plus, Star, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SaveButton } from './SaveButton';
import { SavedStatusPill, type SaveStatus } from './SavedStatusPill';

export type ModelerSavePhase = 'saved' | 'dirty' | 'saving' | 'error';

export type ModelerFileToolbarProps = {
  savePhase: ModelerSavePhase;
  fileLoaded: boolean;
  canManage: boolean;
  isPrimary: boolean;
  isBpmn: boolean;
  isDiagram: boolean;
  onSave: () => void;
  onDownload: () => void;
  onNewFile?: () => void;
  onDelete?: () => void;
  onSetPrimary?: () => void;
  onViewXml?: () => void;
};

function pillStatus(phase: ModelerSavePhase): SaveStatus {
  if (phase === 'saving') return 'saving';
  if (phase === 'error') return 'error';
  return 'saved';
}

/** File actions on the process-modeler header — Save/Download plus the
 * old-canvas chrome (new file, delete non-primary, set primary, view XML).
 * Start-process and save-as-template stay off this bar. */
export function ModelerFileToolbar({
  savePhase,
  fileLoaded,
  canManage,
  isPrimary,
  isBpmn,
  isDiagram,
  onSave,
  onDownload,
  onNewFile,
  onDelete,
  onSetPrimary,
  onViewXml,
}: ModelerFileToolbarProps) {
  const canDelete = canManage && !isPrimary && Boolean(onDelete);
  const canPrimary = canManage && isBpmn && !isPrimary && Boolean(onSetPrimary);

  return (
    <div className="flex flex-none flex-wrap items-center justify-end gap-2">
      {savePhase === 'dirty' ? (
        <SaveButton onClick={onSave} />
      ) : (
        <SavedStatusPill status={pillStatus(savePhase)} />
      )}
      {canManage && onNewFile ? (
        <Button type="button" variant="outline" size="sm" onClick={onNewFile} className="gap-1.5">
          <Plus className="size-3.5" strokeWidth={2.2} />
          New file
        </Button>
      ) : null}
      {canPrimary ? (
        <Button type="button" variant="outline" size="sm" onClick={onSetPrimary} className="gap-1.5">
          <Star className="size-3.5" strokeWidth={2.2} />
          Set as primary
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
          View XML
        </Button>
      ) : null}
      <Button
        type="button"
        variant="pill-info"
        size="pill"
        onClick={onDownload}
        disabled={!fileLoaded}
        className="gap-1.5"
      >
        <Download className="size-3.5" strokeWidth={2.2} />
        Download
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
          Delete
        </Button>
      ) : null}
    </div>
  );
}
