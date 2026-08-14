// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Action strip above the diagram editor. Every control is one entry in a slot list
// that carries its CASL gate (verb + permission target URI), whether the host offers
// it at all, and its markup — so the permission wrapper is written once instead of
// once per button. The data-testid values and the t() keys are contracts with the e2e
// suite and the locale bundles and are therefore fixed; the arrangement is m8flow's.

import { Fragment } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Stack } from '@mui/material';
import { Can } from '@casl/react';
import type { Ability } from '@casl/ability';
import ConfirmButton from '@spiffworkflow-frontend/components/ConfirmButton';
import ProcessInstanceRun from '@spiffworkflow-frontend/components/ProcessInstanceRun';
import type { ProcessModel } from '@spiffworkflow-frontend/interfaces';

/** Permission target URIs the toolbar checks against. */
export type DiagramToolbarTargetUris = {
  processModelFileShowPath: string;
  processModelShowPath: string;
};

// What is on screen and what the caller is allowed to do with it.
type ToolbarContext = {
  diagramType: string;
  fileName?: string;
  isPrimaryFile?: boolean;
  processModel?: ProcessModel | null;
  canViewXml: boolean;
  targetUris: DiagramToolbarTargetUris;
  ability: Ability;
};

// One callback per action; the host owns the actual work (save, navigate, download).
type ToolbarActions = {
  onSave: () => void;
  onDelete: () => void;
  onSetPrimaryFile: () => void;
  onDownload: () => void;
  onViewXml: () => void;
};

// Host-side switches. The *Available flags let read-only surfaces (template file
// views) drop a slot that CASL would otherwise permit; both default to on.
type ToolbarSlotOptions = {
  disableSaveButton?: boolean;
  onSetPrimaryFileAvailable?: boolean;
  onDeleteAvailable?: boolean;
  onViewXmlAvailable?: boolean;
  referencesButton: ReactNode;
  activeUserElement?: ReactElement;
};

export type DiagramEditorToolbarProps = ToolbarContext &
  ToolbarActions &
  ToolbarSlotOptions;

type ToolbarSlot = {
  key: string;
  // CASL verb and subject required to see the slot; omitted when it is ungated.
  gate?: { verb: 'GET' | 'PUT' | 'DELETE'; on: string };
  // False when the host suppresses the slot or its preconditions are not met.
  offered: boolean;
  control: ReactNode;
};

export default function DiagramEditorToolbar(props: DiagramEditorToolbarProps) {
  const { t } = useTranslation();
  const { ability, fileName, processModel, targetUris } = props;

  if (props.diagramType === 'readonly') {
    return null;
  }

  const filePath = targetUris.processModelFileShowPath;
  // Viewing the XML form is an editor affordance, so it also needs write access.
  const mayEditFile = ability.can('PUT', filePath);

  const slots: ToolbarSlot[] = [
    {
      key: 'save',
      gate: { verb: 'PUT', on: filePath },
      offered: true,
      control: (
        <Button
          variant="contained"
          data-testid="process-model-file-save-button"
          disabled={props.disableSaveButton}
          onClick={props.onSave}
        >
          {t('save')}
        </Button>
      ),
    },
    {
      key: 'run',
      offered: !!processModel,
      control: processModel ? (
        <ProcessInstanceRun processModel={processModel} />
      ) : null,
    },
    {
      key: 'delete',
      gate: { verb: 'DELETE', on: filePath },
      // The primary file cannot be deleted on its own — the model owns it.
      offered:
        props.onDeleteAvailable !== false && !!fileName && !props.isPrimaryFile,
      control: (
        <ConfirmButton
          data-testid="process-model-file-delete-button"
          description={t('delete_file_description', { file: fileName })}
          onConfirmation={props.onDelete}
          buttonLabel={t('delete')}
        />
      ),
    },
    {
      key: 'set-primary',
      gate: { verb: 'PUT', on: targetUris.processModelShowPath },
      offered: !!props.onSetPrimaryFileAvailable,
      control: (
        <Button
          variant="contained"
          data-testid="diagram-set-primary-file-button"
          onClick={props.onSetPrimaryFile}
        >
          {t('diagram_set_as_primary_file')}
        </Button>
      ),
    },
    {
      key: 'download',
      gate: { verb: 'GET', on: filePath },
      offered: true,
      control: (
        <Button
          variant="contained"
          data-testid="diagram-download-button"
          onClick={props.onDownload}
        >
          {t('diagram_download')}
        </Button>
      ),
    },
    {
      key: 'view-xml',
      gate: { verb: 'GET', on: filePath },
      offered:
        props.onViewXmlAvailable !== false && props.canViewXml && mayEditFile,
      control: (
        <Button
          variant="contained"
          data-testid="diagram-view-xml-button"
          onClick={props.onViewXml}
        >
          {t('diagram_view_xml')}
        </Button>
      ),
    },
    {
      key: 'references',
      offered: !!props.referencesButton,
      control: props.referencesButton,
    },
    {
      // Co-editor presence is only meaningful to someone who can save the file.
      key: 'active-users',
      gate: { verb: 'PUT', on: filePath },
      offered: !!props.activeUserElement,
      control: props.activeUserElement ?? null,
    },
  ];

  return (
    <Stack sx={{ mt: 2 }} direction="row" spacing={2}>
      {slots
        .filter((slot) => slot.offered)
        .map(({ key, gate, control }) =>
          gate ? (
            <Can key={key} I={gate.verb} a={gate.on} ability={ability}>
              {control}
            </Can>
          ) : (
            <Fragment key={key}>{control}</Fragment>
          ),
        )}
    </Stack>
  );
}
