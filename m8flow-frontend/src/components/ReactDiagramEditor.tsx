// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// The bpmn-js / dmn-js CSS imports below are fixed asset paths published by
// those packages; they are interface, not expression, and must match exactly.

import React, { useState } from 'react';
import { Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import 'bpmn-js/dist/assets/diagram-js.css';
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css';
import '@spiffworkflow-frontend/bpmn-js-properties-panel.css';
import 'bpmn-js/dist/assets/bpmn-js.css';
import 'dmn-js/dist/assets/diagram-js.css';
import 'dmn-js/dist/assets/dmn-js-decision-table-controls.css';
import 'dmn-js/dist/assets/dmn-js-decision-table.css';
import 'dmn-js/dist/assets/dmn-js-drd.css';
import 'dmn-js/dist/assets/dmn-js-literal-expression.css';
import 'dmn-js/dist/assets/dmn-js-shared.css';
import 'dmn-js/dist/assets/dmn-font/css/dmn-embedded.css';
import 'dmn-js-properties-panel/dist/assets/properties-panel.css';
import 'bpmn-js-spiffworkflow/app/css/app.css';

import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';

import { useDiagramModeler } from './useDiagramModeler';
import { useDiagramImport } from './useDiagramImport';
import ReferencesModal from './ReferencesModal';
import DiagramEditorToolbar from './DiagramEditorToolbar';
import DiagramEditorControls from './DiagramEditorControls';
import type { ReactDiagramEditorProps } from './ReactDiagramEditor.types';

// Serializes the current diagram to XML and hands it to `onSaved`. Both "save
// to the backend" and "download to disk" start from the same bpmn-js/dmn-js
// export call, they just do something different with the result.
function exportDiagramXml(diagramModelerState: unknown, onSaved: (xml: string) => void) {
  (diagramModelerState as any)
    ?.saveXML({ format: true })
    ?.then((result: any) => onSaved(result.xml));
}

// Triggers a browser download and cleans up the anchor/object URL afterward
// instead of leaking them into the DOM.
function downloadAsFile(contents: string, mimeType: string, downloadName: string) {
  const blob = new Blob([contents], { type: mimeType });
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(blob);
  anchor.download = downloadName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(anchor.href);
}

export default function ReactDiagramEditor(props: ReactDiagramEditorProps) {
  // DiagramSource-ish: what to render and where it came from.
  const { processModelId, diagramType, fileName, url, diagramXML, isPrimaryFile, processModel, callers, tasks } =
    props;
  // DiagramChrome: toolbar switches.
  const { disableSaveButton, hideDeleteButton, hideViewXmlButton, activeUserElement } = props;
  // The handful of DiagramCallbacks this component itself calls; the rest pass
  // straight through to useDiagramModeler below via `props.onX`.
  const { onCallActivityOverlayClick, onDeleteFile, onSetPrimaryFile, saveDiagram } = props;

  const [performingXmlUpdates, setPerformingXmlUpdates] = useState(false);
  const [showingReferences, setShowingReferences] = useState(false);

  const navigate = useNavigate();
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();

  // A read-only diagram exposes no mutating controls, so it asks for no permissions.
  const permissionRequestData: PermissionsToCheck =
    diagramType === 'readonly'
      ? {}
      : {
          [targetUris.processModelShowPath]: ['PUT'],
          [targetUris.processModelFileShowPath]: ['POST', 'GET', 'PUT', 'DELETE'],
        };
  const { ability } = usePermissionFetcher(permissionRequestData);

  const { diagramModelerState, diagramXMLString, setDiagramXMLString, zoom } = useDiagramModeler({
    diagramType,
    setPerformingXmlUpdates,
    onDataStoresRequested: props.onDataStoresRequested,
    onDmnFilesRequested: props.onDmnFilesRequested,
    onElementClick: props.onElementClick,
    onElementsChanged: props.onElementsChanged,
    onJsonSchemaFilesRequested: props.onJsonSchemaFilesRequested,
    onLaunchBpmnEditor: props.onLaunchBpmnEditor,
    onLaunchDmnEditor: props.onLaunchDmnEditor,
    onLaunchJsonSchemaEditor: props.onLaunchJsonSchemaEditor,
    onLaunchMarkdownEditor: props.onLaunchMarkdownEditor,
    onLaunchMessageEditor: props.onLaunchMessageEditor,
    onLaunchScriptEditor: props.onLaunchScriptEditor,
    onMessagesRequested: props.onMessagesRequested,
    onSearchProcessModels: props.onSearchProcessModels,
    onServiceTasksRequested: props.onServiceTasksRequested,
  });

  useDiagramImport({
    diagramModelerState,
    diagramType,
    diagramXML,
    fileName,
    processModelId,
    url,
    tasks,
    onCallActivityOverlayClick,
    performingXmlUpdates,
    setDiagramXMLString,
  });

  const canViewXml = fileName !== undefined;

  function handleSave() {
    if (saveDiagram && diagramModelerState) exportDiagramXml(diagramModelerState, saveDiagram);
  }

  function handleDownload() {
    const downloadName = fileName ?? `${processModelId}.${diagramType}`;
    exportDiagramXml(diagramModelerState, (xml) => downloadAsFile(xml, 'application/xml', downloadName));
  }

  function handleDelete() {
    onDeleteFile?.(fileName);
  }

  function handleSetPrimaryFile() {
    onSetPrimaryFile?.(fileName);
  }

  const referencesButton =
    callers && callers.length > 0 ? (
      <Button variant="contained" data-testid="diagram-references-button" onClick={() => setShowingReferences(true)}>
        {callers.length === 1
          ? t('diagram_references_count', { count: 1 })
          : t('diagram_references_count_plural', { count: callers.length })}
      </Button>
    ) : null;

  return (
    <>
      <DiagramEditorToolbar
        diagramType={diagramType}
        processModelId={processModelId}
        fileName={fileName}
        isPrimaryFile={isPrimaryFile}
        disableSaveButton={disableSaveButton}
        processModel={processModel}
        canViewXml={canViewXml}
        targetUris={targetUris}
        ability={ability}
        onSave={handleSave}
        onDelete={handleDelete}
        onSetPrimaryFile={handleSetPrimaryFile}
        onDownload={handleDownload}
        onViewXml={() =>
          navigate(`/process-models/${processModelId}/form/${fileName}`)
        }
        referencesButton={referencesButton}
        activeUserElement={activeUserElement}
        onSetPrimaryFileAvailable={!!onSetPrimaryFile}
        onDeleteAvailable={!hideDeleteButton}
        onViewXmlAvailable={!hideViewXmlButton}
      />
      <ReferencesModal
        open={showingReferences}
        onClose={() => setShowingReferences(false)}
        callers={callers}
      />
      <DiagramEditorControls
        onZoomIn={() => zoom(1)}
        onZoomOut={() => zoom(-1)}
        onZoomFit={() => zoom(0)}
      />
    </>
  );
}
