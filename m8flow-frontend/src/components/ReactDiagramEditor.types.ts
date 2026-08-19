// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Public prop contract of the m8flow diagram editor. The prop *names* are the API
// surface its call sites already use; the declaration below is m8flow's own
// expression of that surface (grouped by role, callbacks folded into one mapped
// type) rather than a per-handler restatement.

import type React from 'react';
import type {
  ProcessModel,
  ProcessReference,
  BasicTask,
} from '@spiffworkflow-frontend/interfaces';

// Every editor callback shares one loose signature: the host forwards whatever the
// bpmn-js / dmn-js event handed it and ignores the return value.
type DiagramCallback = (..._args: any[]) => any;

// The callback surface, as a set of names rather than a field per handler.
type DiagramCallbackName =
  | 'onCallActivityOverlayClick'
  | 'onDataStoresRequested'
  | 'onDeleteFile'
  | 'onDmnFilesRequested'
  | 'onElementClick'
  | 'onElementsChanged'
  | 'onJsonSchemaFilesRequested'
  | 'onLaunchBpmnEditor'
  | 'onLaunchDmnEditor'
  | 'onLaunchJsonSchemaEditor'
  | 'onLaunchMarkdownEditor'
  | 'onLaunchMessageEditor'
  | 'onLaunchScriptEditor'
  | 'onMessagesRequested'
  | 'onSearchProcessModels'
  | 'onServiceTasksRequested'
  | 'onSetPrimaryFile'
  | 'saveDiagram';

// All optional: a given host (editor, read-only viewer, template preview) wires up
// only the interactions it supports.
type DiagramCallbacks = Partial<Record<DiagramCallbackName, DiagramCallback>>;

// What to render, where it came from, and what may be done to it.
type DiagramSource = {
  processModelId: string;
  diagramType: string;
  fileName?: string;
  url?: string;
  diagramXML?: string | null;
  isPrimaryFile?: boolean;
  processModel?: ProcessModel | null;
  callers?: ProcessReference[];
  tasks?: BasicTask[] | null;
};

// Toolbar/chrome switches. hideDeleteButton / hideViewXmlButton are m8flow
// additions used by template file views, which are read-only to the tenant.
type DiagramChrome = {
  disableSaveButton?: boolean;
  hideDeleteButton?: boolean;
  hideViewXmlButton?: boolean;
  activeUserElement?: React.ReactElement;
};

export type ReactDiagramEditorProps = DiagramSource &
  DiagramChrome &
  DiagramCallbacks;

export const FIT_VIEWPORT = 'fit-viewport';
