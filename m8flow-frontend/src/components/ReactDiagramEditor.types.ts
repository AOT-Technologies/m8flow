// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: Sartography and the SpiffArena contributors
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Derived from spiffworkflow-frontend/src/components/ReactDiagramEditor.tsx in SpiffArena
// (https://github.com/sartography/spiff-arena), licensed LGPL-2.1-or-later.
// AOT's modifications to this file are released under the same licence.
// See LICENSES/LGPL-2.1-or-later.txt and NOTICE.

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
  /** When true, hides the Delete button in the toolbar (e.g. template file views). */
  hideDeleteButton?: boolean;
  /** When true, hides the View XML button in the toolbar (e.g. template file views). */
  hideViewXmlButton?: boolean;
};

export const FIT_VIEWPORT = 'fit-viewport';
