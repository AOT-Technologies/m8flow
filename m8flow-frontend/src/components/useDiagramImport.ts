// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Loads a BPMN/DMN diagram into a bpmn-js/dmn-js modeler and, for BPMN, paints
// per-task run state onto the canvas. Re-expressed independently of upstream; the
// only shared surface is the functional contract it must honour — the CSS marker
// class names (defined in the stylesheets), the bpmn-js canvas/overlay API, and the
// `{{PROCESS_ID}}`/`{{DECISION_ID}}` placeholders the seed-diagram templates carry.

import React, { useEffect, useRef } from 'react';
import HttpService from '@spiffworkflow-frontend/services/HttpService';
import {
  convertSvgElementToHtmlString,
  getBpmnProcessIdentifiers,
  makeid,
} from '@spiffworkflow-frontend/helpers';
import CallActivityNavigateArrowUp from '@spiffworkflow-frontend/icons/call_activity_navigate_arrow_up.svg';
import type { BasicTask } from '@spiffworkflow-frontend/interfaces';
import { FIT_VIEWPORT } from './ReactDiagramEditor.types';

export type UseDiagramImportOptions = {
  diagramModelerState: any;
  diagramType: string;
  diagramXML?: string | null;
  fileName?: string;
  processModelId: string;
  url?: string;
  tasks?: BasicTask[] | null;
  onCallActivityOverlayClick?: (..._args: any[]) => any;
  performingXmlUpdates: boolean;
  setDiagramXMLString: (value: string) => void;
};

// The marker class the stylesheet defines for each task run state. Absent state ->
// no marker. Data-driven so adding a state is a one-line change.
const TASK_STATE_MARKER: Readonly<Record<string, string>> = {
  COMPLETED: 'completed-task-highlight',
  READY: 'active-task-highlight',
  WAITING: 'active-task-highlight',
  STARTED: 'active-task-highlight',
  CANCELLED: 'cancelled-task-highlight',
  ERROR: 'errored-task-highlight',
};

// Synthetic spec ids bpmn-js never renders as real shapes, plus the join/boundary
// helper specs — none of these can carry a canvas marker.
const NON_HIGHLIGHTABLE_SPEC = /^(Root|Start|End)$|EndJoin|BoundaryEvent(Parent|Join|Split)/;

// bpmn-js throws this exact TypeError when a marker/overlay targets an element that
// is not on the current canvas; it is expected and swallowed, anything else re-throws.
const BPMN_MISSING_ELEMENT_ERROR = "Cannot read properties of undefined (reading 'id')";

function isMultiInstanceChild(task: BasicTask): boolean {
  return 'iteration' in (task.runtime_info ?? {});
}

function canHighlightTask(task: BasicTask): boolean {
  return (
    !isMultiInstanceChild(task) && !NON_HIGHLIGHTABLE_SPEC.test(task.bpmn_identifier)
  );
}

// bpmn-js canvas/overlay calls only succeed for elements in the diagram being shown;
// run `op` and let the "missing element" TypeError pass, re-throwing anything else.
function withCanvasElement(op: () => void): void {
  try {
    op();
  } catch (bpmnError: any) {
    if (bpmnError?.message !== BPMN_MISSING_ELEMENT_ERROR) {
      throw bpmnError;
    }
  }
}

export function useDiagramImport(options: UseDiagramImportOptions) {
  const {
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
  } = options;

  // Keep the latest options in a ref so the effect below can read current values
  // without listing them as dependencies (it must only re-run per modeler instance).
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  // The last-loaded source key, so an unchanged diagram is never re-imported.
  const lastLoadedSourceRef = useRef<string | null | undefined>(null);

  useEffect(() => {
    if (!diagramModelerState) return undefined;

    const reportError = (err: any) => console.error('ERROR:', err);

    const markTaskState = (
      canvas: any,
      task: BasicTask,
      markerClass: string,
      processIdentifiers: string[],
    ) => {
      if (!canHighlightTask(task)) return;
      if (!processIdentifiers.includes(task.bpmn_process_definition_identifier)) return;
      withCanvasElement(() => canvas.addMarker(task.bpmn_identifier, markerClass));
    };

    const buildDrilldownButton = (task: BasicTask): HTMLElement | null => {
      const arrow = convertSvgElementToHtmlString(
        React.createElement(CallActivityNavigateArrowUp, null),
      );
      const holder = document.createElement('template');
      holder.innerHTML = `<button class="bjs-drilldown">${arrow}</button>`.trim();
      const button = holder.content.firstChild as HTMLElement | null;
      if (button) {
        const forward = (nativeEvent: any) =>
          optsRef.current.onCallActivityOverlayClick?.(task, nativeEvent);
        button.addEventListener('click', forward);
        button.addEventListener('auxclick', forward);
      }
      return button;
    };

    const addCallActivityDrilldown = (task: BasicTask, processIdentifiers: string[]) => {
      const { onCallActivityOverlayClick: onClick, diagramType: dt } = optsRef.current;
      if (isMultiInstanceChild(task) || !onClick || dt !== 'readonly' || !diagramModelerState) {
        return;
      }
      if (!processIdentifiers.includes(task.bpmn_process_definition_identifier)) return;
      const button = buildDrilldownButton(task);
      if (!button) return;
      withCanvasElement(() =>
        diagramModelerState.get('overlays').add(task.bpmn_identifier, 'drilldown', {
          position: { bottom: -10, right: -8 },
          html: button,
        }),
      );
    };

    const paintTaskStates = () => {
      const { diagramType: dt, tasks: currentTasks } = optsRef.current;
      if (dt === 'dmn' || !currentTasks) return;

      const canvas = diagramModelerState.get('canvas');
      canvas.zoom(FIT_VIEWPORT, 'auto');
      const processIdentifiers = getBpmnProcessIdentifiers(canvas.getRootElement());

      currentTasks.forEach((task: BasicTask) => {
        const markerClass = TASK_STATE_MARKER[task.state];
        if (markerClass) {
          markTaskState(canvas, task, markerClass, processIdentifiers);
        }
        const isNavigableCallActivity =
          task.typename === 'CallActivity' &&
          !['FUTURE', 'LIKELY', 'MAYBE'].includes(task.state);
        if (isNavigableCallActivity) {
          addCallActivityDrilldown(task, processIdentifiers);
        }
      });
    };

    const onImportDone = (event: any) => {
      if (event.error) {
        reportError(event.error);
        return;
      }
      paintTaskStates();
    };

    // Seed diagrams ship with a placeholder id the editor stamps unique on first load.
    const seedWithUniqueId = (template: string, token: string, prefix: string) => {
      const uniqueId = `${prefix}_${makeid(7)}`;
      optsRef.current.setDiagramXMLString(template.replaceAll(token, uniqueId));
    };

    const loadFromUrl = (source: string, transform?: (text: string) => void) => {
      fetch(source)
        .then((response) => response.text())
        .then(transform ?? (() => {}))
        .catch(reportError);
    };

    const loadFromBackendFile = () => {
      const { processModelId: pmId, fileName: fn } = optsRef.current;
      HttpService.makeCallToBackend({
        path: `/process-models/${pmId}/files/${fn}`,
        successCallback: (result: any) =>
          optsRef.current.setDiagramXMLString(result.file_contents),
      });
    };

    diagramModelerState.on('import.done', onImportDone);
    const detach = () => diagramModelerState.off('import.done', onImportDone);

    // Read the current source from the ref; skip loading mid-XML-update.
    const {
      diagramXML: xml,
      url: urlVal,
      fileName: fn,
      diagramType: dt,
      performingXmlUpdates: performing,
    } = optsRef.current;
    if (performing) return detach;

    const sourceKey = xml || urlVal || fn || dt;
    if (lastLoadedSourceRef.current !== sourceKey) {
      lastLoadedSourceRef.current = sourceKey;
      if (xml) {
        optsRef.current.setDiagramXMLString(xml);
      } else if (urlVal) {
        loadFromUrl(urlVal);
      } else if (fn) {
        loadFromBackendFile();
      } else if (dt === 'dmn') {
        loadFromUrl('/new_dmn_diagram.dmn', (text) =>
          seedWithUniqueId(text, '{{DECISION_ID}}', 'decision'),
        );
      } else {
        loadFromUrl('/new_bpmn_diagram.bpmn', (text) =>
          seedWithUniqueId(text, '{{PROCESS_ID}}', 'Process'),
        );
      }
    }

    return detach;
    // Re-run only when the modeler instance changes; all other inputs come from optsRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramModelerState]);
}
