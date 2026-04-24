import React, { useEffect, useRef, useState, useCallback } from 'react';
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

  const callbacksRef = useRef({
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
  });
  useEffect(() => {
    callbacksRef.current = {
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
    };
  });

  const [diagramXMLString, setDiagramXMLString] = useState('');
  const [diagramModelerState, setDiagramModelerState] = useState<any>(null);
  const keepServiceGroupOpenUntilRef = useRef(0);

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

    const propertiesPanelParent = document.getElementById(panelId);

    // ── Service Properties Panel Stability ────────────────────────────────────
    // Root cause: bpmn-js-properties-panel rebuilds the entire panel (all groups
    // reset to CLOSED) on every `elements.changed` event. This collapses
    // 'M8flow Service Properties' whenever the user interacts with a Service Task.
    // Also fires on `spiff.service_tasks.requested` during first render.
    //
    // Fix: snapshot open group IDs before each rebuild, restore after via
    // MutationObserver. Guard against click→mutation loops with isRestoring flag.

    // bpmn-js-properties-panel puts 'open' on the HEADER, not the group container
    const isGroupOpen = (group: HTMLElement): boolean => {
      if (group.classList.contains('open')) return true;
      const header = group.querySelector(':scope > .bio-properties-panel-group-header');
      return !!header?.classList.contains('open');
    };

    const getOpenGroupIds = (): string[] => {
      if (!propertiesPanelParent) return [];
      return Array.from(
        propertiesPanelParent.querySelectorAll<HTMLElement>(
          '.bio-properties-panel-group[data-group-id]',
        ),
      )
        .filter(isGroupOpen)
        .map((g) => g.getAttribute('data-group-id') || '')
        .filter(Boolean);
    };

    const openGroupSnapshotRef = { current: [] as string[] };
    let isRestoring = false;
    let restoreTimerId: ReturnType<typeof setTimeout> | null = null;

    const openGroupById = (groupId: string): void => {
      if (!propertiesPanelParent) return;
      const group = propertiesPanelParent.querySelector<HTMLElement>(
        `.bio-properties-panel-group[data-group-id="${groupId}"]`,
      );
      if (!group || isGroupOpen(group)) return;
      const btn = group.querySelector<HTMLElement>(
        '.bio-properties-panel-group-header-button, .bio-properties-panel-group-header',
      );
      btn?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    };

    const restoreGroups = () => {
      if (isRestoring) return;
      if (Date.now() > keepServiceGroupOpenUntilRef.current) return;
      const snapshot = openGroupSnapshotRef.current;
      if (!snapshot.length) return;
      isRestoring = true;
      try {
        snapshot.forEach((id) => openGroupById(id));
      } finally {
        window.requestAnimationFrame(() => { isRestoring = false; });
      }
    };

    const propertiesPanelObserver = new MutationObserver(() => {
      if (isRestoring) return;
      if (Date.now() > keepServiceGroupOpenUntilRef.current) return;
      if (restoreTimerId !== null) clearTimeout(restoreTimerId);
      restoreTimerId = setTimeout(() => { restoreTimerId = null; restoreGroups(); }, 30);
    });

    if (propertiesPanelParent) {
      propertiesPanelObserver.observe(propertiesPanelParent, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['class'], // catch group collapse via CSS class toggle on header
      });
    }

    // Capture snapshot on any click inside the panel.
    // Uses capture phase so we read state BEFORE the click target's handler fires.
    const onPanelClick = (e: Event) => {
      if (isRestoring) return;
      const target = e.target as HTMLElement | null;
      if (!target || !propertiesPanelParent) return;

      // If user clicked the service properties group header → intentional close.
      // Clear the guard so the MutationObserver does not re-open it.
      const serviceGroup = propertiesPanelParent.querySelector<HTMLElement>(
        '.bio-properties-panel-group[data-group-id="group-service_task_properties"]',
      );
      const serviceHeader = serviceGroup?.querySelector<HTMLElement>(
        ':scope > .bio-properties-panel-group-header',
      );
      if (serviceHeader && (serviceHeader === target || serviceHeader.contains(target))) {
        openGroupSnapshotRef.current = [];
        keepServiceGroupOpenUntilRef.current = 0;
        return;
      }

      // Any other click: if service group is open, pin it open (children can still toggle freely).
      // We only restore group-service_task_properties, never child groups.
      if (serviceGroup && isGroupOpen(serviceGroup)) {
        openGroupSnapshotRef.current = ['group-service_task_properties'];
        keepServiceGroupOpenUntilRef.current = Date.now() + 3000;
      }
    };
    if (propertiesPanelParent) {
      propertiesPanelParent.addEventListener('click', onPanelClick, true);
    }
    // ── End panel stability ──────────────────────────────────────────────────

    let diagramModeler: any = null;
    if (diagramType === 'bpmn') {
      diagramModeler = new BpmnModeler({
        container: '#canvas',
        keyboard: { bindTo: document },
        propertiesPanel: { parent: `#${panelId}` },
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
          propertiesPanel: { parent: `#${panelId}` },
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
      const cb = callbacksRef.current;
      if (cb.onLaunchScriptEditor) {
        cb.setPerformingXmlUpdates(true);
        const modeling = diagramModeler.get('modeling');
        cb.onLaunchScriptEditor(element, script, scriptType, eventBus, modeling);
      }
    }

    function handleLaunchMarkdownEditor(
      element: any,
      value: string,
      eventBus: any,
    ) {
      const cb = callbacksRef.current;
      if (cb.onLaunchMarkdownEditor) {
        cb.setPerformingXmlUpdates(true);
        cb.onLaunchMarkdownEditor(element, value, eventBus);
      }
    }

    function handleElementClick(event: any) {
      const cb = callbacksRef.current;
      if (cb.onElementClick) {
        const canvas = diagramModeler.get('canvas');
        const bpmnProcessIdentifiers = getBpmnProcessIdentifiers(
          canvas.getRootElement(),
        );
        cb.onElementClick(event.element, bpmnProcessIdentifiers);
      }
    }

    function handleServiceTasksRequested(event: any) {
      // spiff.service_tasks.requested fires synchronously during the first render
      // of ServiceTaskOperatorSelect (when serviceTaskOperators === []). The parent
      // makes an async API call; when it returns and the panel rebuilds, this
      // guard ensures open groups are restored by the MutationObserver.
      const currentlyOpen = getOpenGroupIds();
      if (currentlyOpen.includes('group-service_task_properties')) {
        openGroupSnapshotRef.current = ['group-service_task_properties'];
        keepServiceGroupOpenUntilRef.current = Date.now() + 5000;
      }
      callbacksRef.current.onServiceTasksRequested?.(event);
    }

    function handleDataStoresRequested(event: any) {
      callbacksRef.current.onDataStoresRequested?.(event);
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
      callbacksRef.current.onLaunchBpmnEditor?.(event.processId);
    });

    diagramModeler.on('spiff.file.edit', (event: any) => {
      const { error, element, value, eventBus } = event;
      if (error) console.error(error);
      callbacksRef.current.onLaunchJsonSchemaEditor?.(element, value, eventBus);
    });

    diagramModeler.on('spiff.dmn.edit', (event: any) => {
      callbacksRef.current.onLaunchDmnEditor?.(event.value);
    });

    diagramModeler.on('element.click', (element: any) => {
      handleElementClick(element);
    });

    diagramModeler.on('elements.changed', (event: any) => {
      // Snapshot open groups BEFORE the panel rebuilds
      const currentlyOpen = getOpenGroupIds();
      if (currentlyOpen.includes('group-service_task_properties')) {
        openGroupSnapshotRef.current = ['group-service_task_properties'];
        keepServiceGroupOpenUntilRef.current = Date.now() + 3000;
      }
      callbacksRef.current.onElementsChanged?.(event);
    });


    diagramModeler.on('spiff.service_tasks.requested', handleServiceTasksRequested);
    diagramModeler.on('spiff.data_stores.requested', handleDataStoresRequested);

    diagramModeler.on('spiff.json_schema_files.requested', (event: any) => {
      callbacksRef.current.onJsonSchemaFilesRequested?.(event);
      handleServiceTasksRequested(event);
    });

    diagramModeler.on('spiff.dmn_files.requested', (event: any) => {
      callbacksRef.current.onDmnFilesRequested?.(event);
    });

    diagramModeler.on('spiff.messages.requested', (event: any) => {
      callbacksRef.current.onMessagesRequested?.(event);
    });

    diagramModeler.on('spiff.callactivity.search', (event: any) => {
      const cb = callbacksRef.current;
      if (cb.onSearchProcessModels) {
        cb.onSearchProcessModels(event.value, event.eventBus, event.element);
      }
    });

    diagramModeler.on('spiff.message.edit', (event: any) => {
      callbacksRef.current.onLaunchMessageEditor?.(event);
    });

    return () => {
      if (propertiesPanelParent) {
        propertiesPanelParent.removeEventListener('click', onPanelClick, true);
      }
      if (restoreTimerId !== null) {
        clearTimeout(restoreTimerId);
        restoreTimerId = null;
      }
      propertiesPanelObserver.disconnect();
      if (diagramModeler) {
        diagramModeler.destroy();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramType]);

  const lastImportedXMLRef = useRef<string | null>(null);

  useEffect(() => {
    if (!diagramXMLString || !diagramModelerState) return;
    if (lastImportedXMLRef.current === diagramXMLString) return;
    lastImportedXMLRef.current = diagramXMLString;

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