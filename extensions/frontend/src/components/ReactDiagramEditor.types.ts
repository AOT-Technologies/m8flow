import React from 'react';
import { ProcessModel, ProcessReference, BasicTask } from '@spiffworkflow-frontend/interfaces';

export type ReactDiagramEditorProps = {
  processModelId: string;
  diagramType: string;
  activeUserElement?: React.ReactElement;
  callers?: ProcessReference[];
  diagramXML?: string | null;
  disableSaveButton?: boolean;
  fileName?: string;
  isPrimaryFile?: boolean;
  processModel?: ProcessModel | null;
  onCallActivityOverlayClick?: (..._args: any[]) => any;
  onDataStoresRequested?: (..._args: any[]) => any;
  onDeleteFile?: (..._args: any[]) => any;
  onDmnFilesRequested?: (..._args: any[]) => any;
  onElementClick?: (..._args: any[]) => any;
  onElementsChanged?: (..._args: any[]) => any;
  onJsonSchemaFilesRequested?: (..._args: any[]) => any;
  onLaunchBpmnEditor?: (..._args: any[]) => any;
  onLaunchDmnEditor?: (..._args: any[]) => any;
  onLaunchJsonSchemaEditor?: (..._args: any[]) => any;
  onLaunchMarkdownEditor?: (..._args: any[]) => any;
  onLaunchScriptEditor?: (..._args: any[]) => any;
  onLaunchMessageEditor?: (..._args: any[]) => any;
  onMessagesRequested?: (..._args: any[]) => any;
  onSearchProcessModels?: (..._args: any[]) => any;
  onServiceTasksRequested?: (..._args: any[]) => any;
  onSetPrimaryFile?: (..._args: any[]) => any;
  saveDiagram?: (..._args: any[]) => any;
  tasks?: BasicTask[] | null;
  url?: string;
};

export const FIT_VIEWPORT = 'fit-viewport';
