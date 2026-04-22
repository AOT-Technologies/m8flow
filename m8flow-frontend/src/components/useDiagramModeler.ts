import React, { useEffect, useState, useCallback } from 'react';
import BpmnModeler from 'bpmn-js/lib/Modeler';
import BpmnViewer from 'bpmn-js/lib/Viewer';
import {
  BpmnPropertiesPanelModule,
  BpmnPropertiesProviderModule,
  // @ts-expect-error TS(7016) FIXME
} from 'bpmn-js-properties-panel';
// @ts-expect-error TS(7016) FIXME
import CliModule from 'bpmn-js-cli';
// @ts-expect-error TS(7016) FIXME
import DmnModeler from 'dmn-js/lib/Modeler';
import {
  DmnPropertiesPanelModule,
  DmnPropertiesProviderModule,
  // @ts-expect-error TS(7016) FIXME
} from 'dmn-js-properties-panel';
import KeyboardMoveModule from 'diagram-js/lib/navigation/keyboard-move';
import MoveCanvasModule from 'diagram-js/lib/navigation/movecanvas';
import ZoomScrollModule from 'diagram-js/lib/navigation/zoomscroll';
// @ts-expect-error TS(7016) FIXME
import spiffworkflow from 'bpmn-js-spiffworkflow/app/spiffworkflow';
import spiffModdleExtension from 'bpmn-js-spiffworkflow/app/spiffworkflow/moddle/spiffworkflow.json';
import BpmnJsScriptIcon from '@spiffworkflow-frontend/icons/bpmn_js_script_icon.svg';
import { getBpmnProcessIdentifiers } from '@spiffworkflow-frontend/helpers';
import { TASK_METADATA } from '@spiffworkflow-frontend/config';
import { convertSvgElementToHtmlString } from '@spiffworkflow-frontend/helpers';
import { FIT_VIEWPORT } from './ReactDiagramEditor.types';
import type { ReactDiagramEditorProps } from './ReactDiagramEditor.types';

export type UseDiagramModelerOptions = Pick<
  ReactDiagramEditorProps,
  | 'diagramType'
  | 'onDataStoresRequested'
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
> & {
  setPerformingXmlUpdates: (value: boolean) => void;
};

export function useDiagramModeler(options: UseDiagramModelerOptions) {
  const {
    diagramType,
    setPerformingXmlUpdates,
    onDataStoresRequested,
    onDmnFilesRequested,
    onElementClick,
    onElementsChanged,
    onJsonSchemaFilesRequested,
    onLaunchBpmnEditor,
    onLaunchDmnEditor,
    onLaunchJsonSchemaEditor,
    onLaunchMarkdownEditor,
    onLaunchMessageEditor,
    onLaunchScriptEditor,
    onMessagesRequested,
    onSearchProcessModels,
    onServiceTasksRequested,
  } = options;

  const [diagramXMLString, setDiagramXMLString] = useState('');
  const [diagramModelerState, setDiagramModelerState] = useState<any>(null);

  const zoom = useCallback(
    (amount: number) => {
      if (diagramModelerState) {
        let modeler = diagramModelerState as any;
        if (diagramType === 'dmn') {
          modeler = (diagramModelerState as any).getActiveViewer();
        }
        if (modeler) {
          if (amount === 0) {
            const canvas = modeler.get('canvas');
            canvas.zoom(FIT_VIEWPORT, 'auto');
          } else {
            modeler.get('zoomScroll').stepZoom(amount);
          }
        }
      }
    },
    [diagramModelerState, diagramType],
  );

  const fixUnresolvedReferences = useCallback((diagramModelerToUse: any) => {
    diagramModelerToUse.on('import.parse.complete', (event: any) => {
      if (!event.references) return;
      const refs = event.references.filter(
        (r: any) =>
          r.property === 'bpmn:loopDataInputRef' ||
          r.property === 'bpmn:loopDataOutputRef',
      );
      const desc = diagramModelerToUse._moddle.registry.getEffectiveDescriptor(
        'bpmn:ItemAwareElement',
      );
      refs.forEach((ref: any) => {
        const props = {
          id: ref.id,
          name: ref.id ? typeof ref.name === 'undefined' : ref.name,
        };
        const elem = diagramModelerToUse._moddle.create(desc, props);
        elem.$parent = ref.element;
        ref.element.set(ref.property, elem);
      });
    });
  }, []);

  useEffect(() => {
    let canvasClass = 'diagram-editor-canvas';
    if (diagramType === 'readonly') {
      canvasClass = 'diagram-viewer-canvas';
    }
    const panelId =
      diagramType === 'readonly' ? 'hidden-properties-panel' : 'js-properties-panel';
    const temp = document.createElement('template');
    temp.innerHTML = `
      <div class="content with-diagram bpmn-js-container" id="js-drop-zone">
        <div class="canvas ${canvasClass}" id="canvas"></div>
        <div class="properties-panel-parent" id="${panelId}"></div>
      </div>
    `;
    const frag = temp.content;
    const diagramContainerElement = document.getElementById('diagram-container');
    if (diagramContainerElement) {
      diagramContainerElement.innerHTML = '';
      diagramContainerElement.appendChild(frag);
    }

    let diagramModeler: any = null;
    if (diagramType === 'bpmn') {
      diagramModeler = new BpmnModeler({
        container: '#canvas',
        keyboard: { bindTo: document },
        propertiesPanel: { parent: '#js-properties-panel' },
        additionalModules: [
          spiffworkflow,
          BpmnPropertiesPanelModule,
          BpmnPropertiesProviderModule,
          ZoomScrollModule,
          CliModule,
        ],
        cli: { bindTo: 'cli' },
        moddleExtensions: { spiffworkflow: spiffModdleExtension },
      });
    } else if (diagramType === 'dmn') {
      diagramModeler = new DmnModeler({
        container: '#canvas',
        keyboard: { bindTo: document },
        drd: {
          propertiesPanel: { parent: '#js-properties-panel' },
          additionalModules: [
            DmnPropertiesPanelModule,
            DmnPropertiesProviderModule,
            ZoomScrollModule,
          ],
        },
      });
    } else if (diagramType === 'readonly') {
      diagramModeler = new BpmnViewer({
        container: '#canvas',
        keyboard: { bindTo: document },
        additionalModules: [
          KeyboardMoveModule,
          MoveCanvasModule,
          ZoomScrollModule,
        ],
      });
    }

    if (!diagramModeler) {
      setDiagramModelerState(null);
      return;
    }

    function handleLaunchScriptEditor(
      element: any,
      script: string,
      scriptType: string,
      eventBus: any,
    ) {
      if (onLaunchScriptEditor) {
        setPerformingXmlUpdates(true);
        const modeling = diagramModeler.get('modeling');
        onLaunchScriptEditor(element, script, scriptType, eventBus, modeling);
      }
    }

    function handleLaunchMarkdownEditor(
      element: any,
      value: string,
      eventBus: any,
    ) {
      if (onLaunchMarkdownEditor) {
        setPerformingXmlUpdates(true);
        onLaunchMarkdownEditor(element, value, eventBus);
      }
    }

    function handleElementClick(event: any) {
      if (onElementClick) {
        const canvas = diagramModeler.get('canvas');
        const bpmnProcessIdentifiers = getBpmnProcessIdentifiers(
          canvas.getRootElement(),
        );
        onElementClick(event.element, bpmnProcessIdentifiers);
      }
    }

    function handleServiceTasksRequested(event: any) {
      if (onServiceTasksRequested) onServiceTasksRequested(event);
    }

    function handleDataStoresRequested(event: any) {
      if (onDataStoresRequested) onDataStoresRequested(event);
    }

    function createPrePostScriptOverlay(event: any) {
      if (event.element && event.element.type !== 'bpmn:ScriptTask') {
        const preScript =
          event.element.businessObject.extensionElements?.values?.find(
            (extension: any) => extension.$type === 'spiffworkflow:PreScript',
          );
        const postScript =
          event.element.businessObject.extensionElements?.values?.find(
            (extension: any) => extension.$type === 'spiffworkflow:PostScript',
          );
        const overlays = diagramModeler.get('overlays');
        const scriptIcon = convertSvgElementToHtmlString(
          React.createElement(BpmnJsScriptIcon, null),
        );
        if (preScript?.value) {
          overlays.add(event.element.id, {
            position: { bottom: 25, left: 0 },
            html: scriptIcon,
          });
        }
        if (postScript?.value) {
          overlays.add(event.element.id, {
            position: { bottom: 25, right: 25 },
            html: scriptIcon,
          });
        }
      }
    }

    setDiagramModelerState(diagramModeler);

    if (diagramType !== 'readonly') {
      diagramModeler.on('shape.added', (event: any) => {
        createPrePostScriptOverlay(event);
      });
    }

    diagramModeler.on('spiff.task_metadata_keys.requested', (event: any) => {
      event.eventBus.fire('spiff.task_metadata_keys.returned', {
        keys: TASK_METADATA,
      });
    });

    diagramModeler.on('spiff.script.edit', (event: any) => {
      const { error, element, scriptType, script, eventBus } = event;
      if (error) console.error(error);
      handleLaunchScriptEditor(element, script, scriptType, eventBus);
    });

    diagramModeler.on('spiff.markdown.edit', (event: any) => {
      const { error, element, value, eventBus } = event;
      if (error) console.error(error);
      handleLaunchMarkdownEditor(element, value, eventBus);
    });

    diagramModeler.on('spiff.callactivity.edit', (event: any) => {
      if (onLaunchBpmnEditor) onLaunchBpmnEditor(event.processId);
    });

    diagramModeler.on('spiff.file.edit', (event: any) => {
      const { error, element, value, eventBus } = event;
      if (error) console.error(error);
      if (onLaunchJsonSchemaEditor) onLaunchJsonSchemaEditor(element, value, eventBus);
    });

    diagramModeler.on('spiff.dmn.edit', (event: any) => {
      if (onLaunchDmnEditor) onLaunchDmnEditor(event.value);
    });

    diagramModeler.on('element.click', (element: any) => {
      handleElementClick(element);
    });

    diagramModeler.on('elements.changed', (event: any) => {
      if (onElementsChanged) onElementsChanged(event);
    });

    diagramModeler.on('spiff.service_tasks.requested', handleServiceTasksRequested);
    diagramModeler.on('spiff.data_stores.requested', handleDataStoresRequested);

    diagramModeler.on('spiff.json_schema_files.requested', (event: any) => {
      if (onJsonSchemaFilesRequested) onJsonSchemaFilesRequested(event);
      handleServiceTasksRequested(event);
    });

    diagramModeler.on('spiff.dmn_files.requested', (event: any) => {
      if (onDmnFilesRequested) onDmnFilesRequested(event);
    });

    diagramModeler.on('spiff.messages.requested', (event: any) => {
      if (onMessagesRequested) onMessagesRequested(event);
    });

    diagramModeler.on('spiff.callactivity.search', (event: any) => {
      if (onSearchProcessModels) {
        onSearchProcessModels(event.value, event.eventBus, event.element);
      }
    });

    diagramModeler.on('spiff.message.edit', (event: any) => {
      if (onLaunchMessageEditor) onLaunchMessageEditor(event);
    });
  }, [
    diagramType,
    setPerformingXmlUpdates,
    onDataStoresRequested,
    onDmnFilesRequested,
    onElementClick,
    onElementsChanged,
    onJsonSchemaFilesRequested,
    onLaunchBpmnEditor,
    onLaunchDmnEditor,
    onLaunchJsonSchemaEditor,
    onLaunchMarkdownEditor,
    onLaunchMessageEditor,
    onLaunchScriptEditor,
    onMessagesRequested,
    onSearchProcessModels,
    onServiceTasksRequested,
  ]);

  useEffect(() => {
    if (!diagramXMLString || !diagramModelerState) return;
    diagramModelerState.importXML(diagramXMLString);
    zoom(0);
    if (diagramType !== 'dmn') {
      fixUnresolvedReferences(diagramModelerState);
    }
  }, [diagramXMLString, diagramModelerState, diagramType, zoom, fixUnresolvedReferences]);

  return {
    diagramModelerState,
    diagramXMLString,
    setDiagramXMLString,
    zoom,
    fixUnresolvedReferences,
  };
}
