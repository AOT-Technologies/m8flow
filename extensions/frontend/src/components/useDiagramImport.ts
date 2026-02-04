import React, { useEffect } from 'react';
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

  useEffect(() => {
    const taskSpecsThatCannotBeHighlighted = ['Root', 'Start', 'End'];

    if (!diagramModelerState) return undefined;
    if (performingXmlUpdates) return undefined;

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
      if (
        taskIsMultiInstanceChild(task) ||
        !onCallActivityOverlayClick ||
        diagramType !== 'readonly' ||
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
          onCallActivityOverlayClick(task, newEvent);
        });
        button.addEventListener('auxclick', (newEvent: any) => {
          onCallActivityOverlayClick(task, newEvent);
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
      if (diagramType === 'dmn') return;

      const canvas = diagramModelerState.get('canvas');
      canvas.zoom(FIT_VIEWPORT, 'auto');

      if (tasks) {
        const bpmnProcessIdentifiers = getBpmnProcessIdentifiers(
          canvas.getRootElement(),
        );
        tasks.forEach((task: BasicTask) => {
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
      setDiagramXMLString(newText);
    }

    function bpmnTextHandler(text: string) {
      const processId = `Process_${makeid(7)}`;
      const newText = text.replaceAll('{{PROCESS_ID}}', processId);
      setDiagramXMLString(newText);
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
      setDiagramXMLString(result.file_contents);
    }

    function fetchDiagramFromJsonAPI() {
      HttpService.makeCallToBackend({
        path: `/process-models/${processModelId}/files/${fileName}`,
        successCallback: setDiagramXMLStringFromResponseJson,
      });
    }

    (diagramModelerState as any).on('import.done', onImportDone);

    if (diagramXML) {
      setDiagramXMLString(diagramXML);
      return undefined;
    }

    if (!diagramXML) {
      if (url) {
        fetchDiagramFromURL(url);
        return undefined;
      }
      if (fileName) {
        fetchDiagramFromJsonAPI();
        return undefined;
      }
      let newDiagramFileName = 'new_bpmn_diagram.bpmn';
      let textHandler = bpmnTextHandler;
      if (diagramType === 'dmn') {
        newDiagramFileName = 'new_dmn_diagram.dmn';
        textHandler = dmnTextHandler;
      }
      fetchDiagramFromURL(`/${newDiagramFileName}`, textHandler);
      return undefined;
    }

    return undefined;
  }, [
    diagramModelerState,
    diagramType,
    diagramXML,
    fileName,
    onCallActivityOverlayClick,
    performingXmlUpdates,
    processModelId,
    setDiagramXMLString,
    tasks,
    url,
  ]);
}
