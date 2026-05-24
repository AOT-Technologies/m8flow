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

  // ── Stable refs for all mutable option values ──────────────────────────────
  // Storing these in refs means the useEffect never re-runs just because
  // a parent component re-rendered and passed a new function reference.
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  // Track which "source" we last loaded so we never re-import the same diagram.
  const lastLoadedSourceRef = useRef<string | null | undefined>(null);

  useEffect(() => {
    if (!diagramModelerState) return undefined;

    // ── Helpers ──────────────────────────────────────────────────────────────
    const taskSpecsThatCannotBeHighlighted = ['Root', 'Start', 'End'];

    function handleError(err: any) {
      console.error('ERROR:', err);
    }

    function taskIsMultiInstanceChild(task: BasicTask) {
      return Object.hasOwn(task.runtime_info || {}, 'iteration');
    }

    function checkTaskCanBeHighlighted(task: BasicTask) {
      const taskBpmnId = task.bpmn_identifier;
      return (
        !taskIsMultiInstanceChild(task) &&
        !taskSpecsThatCannotBeHighlighted.includes(taskBpmnId) &&
        !taskBpmnId.match(/EndJoin/) &&
        !taskBpmnId.match(/BoundaryEventParent/) &&
        !taskBpmnId.match(/BoundaryEventJoin/) &&
        !taskBpmnId.match(/BoundaryEventSplit/)
      );
    }

    function highlightBpmnIoElement(
      canvas: any,
      task: BasicTask,
      bpmnIoClassName: string,
      bpmnProcessIdentifiers: string[],
    ) {
      if (checkTaskCanBeHighlighted(task)) {
        try {
          if (
            bpmnProcessIdentifiers.includes(
              task.bpmn_process_definition_identifier,
            )
          ) {
            canvas.addMarker(task.bpmn_identifier, bpmnIoClassName);
          }
        } catch (bpmnIoError: any) {
          if (
            bpmnIoError.message !==
            "Cannot read properties of undefined (reading 'id')"
          ) {
            throw bpmnIoError;
          }
        }
      }
    }

    function addOverlayOnCallActivity(
      task: BasicTask,
      bpmnProcessIdentifiers: string[],
    ) {
      // Read from ref so this closure is always up-to-date without being in the dep array
      const { onCallActivityOverlayClick: onOverlayClick, diagramType: dt } = optsRef.current;
      if (
        taskIsMultiInstanceChild(task) ||
        !onOverlayClick ||
        dt !== 'readonly' ||
        !diagramModelerState
      ) {
        return;
      }
      function domify(htmlString: string) {
        const template = document.createElement('template');
        template.innerHTML = htmlString.trim();
        return template.content.firstChild;
      }
      const createCallActivityOverlay = () => {
        const overlays = diagramModelerState.get('overlays');
        const icon = convertSvgElementToHtmlString(
          React.createElement(CallActivityNavigateArrowUp, null),
        );
        const button: any = domify(
          `<button class="bjs-drilldown">${icon}</button>`,
        );
        button.addEventListener('click', (newEvent: any) => {
          onOverlayClick(task, newEvent);
        });
        button.addEventListener('auxclick', (newEvent: any) => {
          onOverlayClick(task, newEvent);
        });
        overlays.add(task.bpmn_identifier, 'drilldown', {
          position: { bottom: -10, right: -8 },
          html: button,
        });
      };
      try {
        if (
          bpmnProcessIdentifiers.includes(
            task.bpmn_process_definition_identifier,
          )
        ) {
          createCallActivityOverlay();
        }
      } catch (bpmnIoError: any) {
        if (
          bpmnIoError.message !==
          "Cannot read properties of undefined (reading 'id')"
        ) {
          throw bpmnIoError;
        }
      }
    }

    function onImportDone(event: any) {
      const { error } = event;
      if (error) {
        handleError(error);
        return;
      }

      // Read latest values from ref at the time this event fires
      const { diagramType: dt, tasks: currentTasks } = optsRef.current;
      if (dt === 'dmn') return;

      const canvas = diagramModelerState.get('canvas');
      canvas.zoom(FIT_VIEWPORT, 'auto');

      if (currentTasks) {
        const bpmnProcessIdentifiers = getBpmnProcessIdentifiers(
          canvas.getRootElement(),
        );
        currentTasks.forEach((task: BasicTask) => {
          let className = '';
          if (task.state === 'COMPLETED') {
            className = 'completed-task-highlight';
          } else if (['READY', 'WAITING', 'STARTED'].includes(task.state)) {
            className = 'active-task-highlight';
          } else if (task.state === 'CANCELLED') {
            className = 'cancelled-task-highlight';
          } else if (task.state === 'ERROR') {
            className = 'errored-task-highlight';
          }
          if (className) {
            highlightBpmnIoElement(
              canvas,
              task,
              className,
              bpmnProcessIdentifiers,
            );
          }
          if (
            task.typename === 'CallActivity' &&
            !['FUTURE', 'LIKELY', 'MAYBE'].includes(task.state)
          ) {
            addOverlayOnCallActivity(task, bpmnProcessIdentifiers);
          }
        });
      }
    }

    function dmnTextHandler(text: string) {
      const decisionId = `decision_${makeid(7)}`;
      const newText = text.replaceAll('{{DECISION_ID}}', decisionId);
      optsRef.current.setDiagramXMLString(newText);
    }

    function bpmnTextHandler(text: string) {
      const processId = `Process_${makeid(7)}`;
      const newText = text.replaceAll('{{PROCESS_ID}}', processId);
      optsRef.current.setDiagramXMLString(newText);
    }

    function fetchDiagramFromURL(
      urlToUse: string,
      textHandler?: (text: string) => void,
    ) {
      fetch(urlToUse)
        .then((response) => response.text())
        .then(textHandler ?? (() => {}))
        .catch((err) => handleError(err));
    }

    function setDiagramXMLStringFromResponseJson(result: any) {
      optsRef.current.setDiagramXMLString(result.file_contents);
    }

    function fetchDiagramFromJsonAPI() {
      const { processModelId: pmId, fileName: fn } = optsRef.current;
      HttpService.makeCallToBackend({
        path: `/process-models/${pmId}/files/${fn}`,
        successCallback: setDiagramXMLStringFromResponseJson,
      });
    }

    // Register the import.done listener once for this modeler instance
    (diagramModelerState as any).on('import.done', onImportDone);

    // ── Load the diagram (only if the source actually changed) ────────────────
    // Read the current source values from the ref so we always use the latest
    // values without needing them in the dependency array.
    const { diagramXML: xml, url: urlVal, fileName: fn, diagramType: dt, performingXmlUpdates: performing } = optsRef.current;

    if (performing) {
      // Don't load while an XML update is in progress
      return () => {
        (diagramModelerState as any).off('import.done', onImportDone);
      };
    }

    const currentSource = xml || urlVal || fn || dt;
    if (lastLoadedSourceRef.current !== currentSource) {
      lastLoadedSourceRef.current = currentSource;
      if (xml) {
        optsRef.current.setDiagramXMLString(xml);
      } else if (urlVal) {
        fetchDiagramFromURL(urlVal);
      } else if (fn) {
        fetchDiagramFromJsonAPI();
      } else {
        let newDiagramFileName = 'new_bpmn_diagram.bpmn';
        let textHandler = bpmnTextHandler;
        if (dt === 'dmn') {
          newDiagramFileName = 'new_dmn_diagram.dmn';
          textHandler = dmnTextHandler;
        }
        fetchDiagramFromURL(`/${newDiagramFileName}`, textHandler);
      }
    }

    return () => {
      (diagramModelerState as any).off('import.done', onImportDone);
    };
    // ── Only re-run when the modeler instance itself changes ─────────────────
    // All other values (diagramXML, fileName, tasks, callbacks, etc.) are read
    // from optsRef at runtime, so they never need to be in this array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramModelerState]);
}
