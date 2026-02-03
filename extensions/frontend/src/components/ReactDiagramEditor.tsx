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

import { useUriListForPermissions } from '@spiffworkflow-frontend/hooks/UriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';

import { useDiagramModeler } from './useDiagramModeler';
import { useDiagramImport } from './useDiagramImport';
import ReferencesModal from './ReferencesModal';
import DiagramEditorToolbar from './DiagramEditorToolbar';
import DiagramEditorControls from './DiagramEditorControls';
import SaveAsTemplateModal from './SaveAsTemplateModal';
import type { ReactDiagramEditorProps } from './ReactDiagramEditor.types';

export default function ReactDiagramEditor(props: ReactDiagramEditorProps) {
  const {
    activeUserElement,
    callers,
    diagramType,
    diagramXML,
    disableSaveButton,
    fileName,
    isPrimaryFile,
    processModel,
    onCallActivityOverlayClick,
    onDeleteFile,
    onSetPrimaryFile,
    processModelId,
    saveDiagram,
    tasks,
    url,
  } = props;

  const [performingXmlUpdates, setPerformingXmlUpdates] = useState(false);
  const [showingReferences, setShowingReferences] = useState(false);
  const [saveAsTemplateModalOpen, setSaveAsTemplateModalOpen] = useState(false);

  const { targetUris } = useUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {};
  if (diagramType !== 'readonly') {
    permissionRequestData[targetUris.processModelShowPath] = ['PUT'];
    permissionRequestData[targetUris.processModelFileShowPath] = [
      'POST',
      'GET',
      'PUT',
      'DELETE',
    ];
  }
  const { ability } = usePermissionFetcher(permissionRequestData);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const {
    diagramModelerState,
    diagramXMLString,
    setDiagramXMLString,
    zoom,
  } = useDiagramModeler({
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

  function handleSave() {
    if (saveDiagram && diagramModelerState) {
      (diagramModelerState as any)
        .saveXML({ format: true })
        .then((xmlObject: any) => saveDiagram(xmlObject.xml));
    }
  }

  function handleDelete() {
    if (onDeleteFile) onDeleteFile(fileName);
  }

  function handleSetPrimaryFile() {
    if (onSetPrimaryFile) onSetPrimaryFile(fileName);
  }

  function downloadXmlFile() {
    (diagramModelerState as any)
      ?.saveXML({ format: true })
      ?.then((xmlObject: any) => {
        const element = document.createElement('a');
        const file = new Blob([xmlObject.xml], {
          type: 'application/xml',
        });
        const downloadFileName = fileName ?? `${processModelId}.${diagramType}`;
        element.href = URL.createObjectURL(file);
        element.download = downloadFileName;
        document.body.appendChild(element);
        element.click();
      });
  }

  const canViewXml = fileName !== undefined;

  const referencesButton =
    callers && callers.length > 0 ? (
      <Button variant="contained" onClick={() => setShowingReferences(true)}>
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
        onDownload={downloadXmlFile}
        onViewXml={() =>
          navigate(`/process-models/${processModelId}/form/${fileName}`)
        }
        onSaveAsTemplate={() => setSaveAsTemplateModalOpen(true)}
        referencesButton={referencesButton}
        activeUserElement={activeUserElement}
        onSetPrimaryFileAvailable={!!onSetPrimaryFile}
      />
      <ReferencesModal
        open={showingReferences}
        onClose={() => setShowingReferences(false)}
        callers={callers}
      />
      <SaveAsTemplateModal
        open={saveAsTemplateModalOpen}
        onClose={() => setSaveAsTemplateModalOpen(false)}
        onSuccess={() => setSaveAsTemplateModalOpen(false)}
        getBpmnXml={() =>
          diagramModelerState
            ? (diagramModelerState as any)
                .saveXML({ format: true })
                .then((xmlObject: any) => xmlObject.xml)
            : Promise.resolve('')
        }
      />
      <DiagramEditorControls
        onZoomIn={() => zoom(1)}
        onZoomOut={() => zoom(-1)}
        onZoomFit={() => zoom(0)}
      />
    </>
  );
}
