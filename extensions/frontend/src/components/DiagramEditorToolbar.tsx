import React from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Stack } from '@mui/material';
import { Can } from '@casl/react';
import ConfirmButton from '@spiffworkflow-frontend/components/ConfirmButton';
import ProcessInstanceRun from '@spiffworkflow-frontend/components/ProcessInstanceRun';
import { ProcessModel } from '@spiffworkflow-frontend/interfaces';
import type { Ability } from '@casl/ability';

export type DiagramEditorToolbarProps = {
  diagramType: string;
  processModelId: string;
  fileName?: string;
  isPrimaryFile?: boolean;
  disableSaveButton?: boolean;
  processModel?: ProcessModel | null;
  canViewXml: boolean;
  targetUris: { processModelFileShowPath: string; processModelShowPath: string };
  ability: Ability;
  onSave: () => void;
  onDelete: () => void;
  onSetPrimaryFile: () => void;
  onDownload: () => void;
  onViewXml: () => void;
  onSaveAsTemplate: () => void;
  referencesButton: React.ReactNode;
  activeUserElement?: React.ReactElement;
  onSetPrimaryFileAvailable?: boolean;
};

export default function DiagramEditorToolbar({
  diagramType,
  processModelId,
  fileName,
  isPrimaryFile,
  disableSaveButton,
  processModel,
  canViewXml,
  targetUris,
  ability,
  onSave,
  onDelete,
  onSetPrimaryFile,
  onDownload,
  onViewXml,
  onSaveAsTemplate,
  referencesButton,
  activeUserElement,
  onSetPrimaryFileAvailable,
}: DiagramEditorToolbarProps) {
  const { t } = useTranslation();

  if (diagramType === 'readonly') {
    return null;
  }

  return (
    <Stack sx={{ mt: 2 }} direction="row" spacing={2}>
      <Can
        I="PUT"
        a={targetUris.processModelFileShowPath}
        ability={ability}
      >
        <Button
          onClick={onSave}
          variant="contained"
          disabled={disableSaveButton}
          data-testid="process-model-file-save-button"
        >
          {t('save')}
        </Button>
      </Can>
      {processModel && <ProcessInstanceRun processModel={processModel} />}
      <Can
        I="DELETE"
        a={targetUris.processModelFileShowPath}
        ability={ability}
      >
        {fileName && !isPrimaryFile && (
          <ConfirmButton
            description={t('delete_file_description', { file: fileName })}
            onConfirmation={onDelete}
            buttonLabel={t('delete')}
          />
        )}
      </Can>
      <Can I="PUT" a={targetUris.processModelShowPath} ability={ability}>
        {onSetPrimaryFileAvailable && (
          <Button onClick={onSetPrimaryFile} variant="contained">
            {t('diagram_set_as_primary_file')}
          </Button>
        )}
      </Can>
      <Can
        I="GET"
        a={targetUris.processModelFileShowPath}
        ability={ability}
      >
        <Button variant="contained" onClick={onDownload}>
          {t('diagram_download')}
        </Button>
      </Can>
      <Can
        I="GET"
        a={targetUris.processModelFileShowPath}
        ability={ability}
      >
        {canViewXml && (
          <Button variant="contained" onClick={onViewXml}>
            {t('diagram_view_xml')}
          </Button>
        )}
      </Can>
      {diagramType === 'bpmn' && (
        <Button
          variant="contained"
          onClick={onSaveAsTemplate}
          data-testid="save-as-template-button"
        >
          Save as Template
        </Button>
      )}
      {referencesButton}
      <Can
        I="PUT"
        a={targetUris.processModelFileShowPath}
        ability={ability}
      >
        {activeUserElement || null}
      </Can>
    </Stack>
  );
}
