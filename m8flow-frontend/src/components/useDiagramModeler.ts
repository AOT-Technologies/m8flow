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
// @ts-expect-error TS(7016) FIXME
import m8flowExternalForm from './bpmn';
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

  // bpmn-js leaves multi-instance loop-data references dangling after parse; synthesize a
  // placeholder ItemAwareElement for each so the moddle tree resolves.
  const LOOP_DATA_REF_PROPS = new Set([
    'bpmn:loopDataInputRef',
    'bpmn:loopDataOutputRef',
  ]);

  const fixUnresolvedReferences = useCallback((diagramModelerToUse: any) => {
    diagramModelerToUse.on('import.parse.complete', (event: any) => {
      const dangling = (event.references ?? []).filter((ref: any) =>
        LOOP_DATA_REF_PROPS.has(ref.property),
      );
      if (dangling.length === 0) return;

      const moddle = diagramModelerToUse._moddle;
      const descriptor = moddle.registry.getEffectiveDescriptor(
        'bpmn:ItemAwareElement',
      );
      dangling.forEach((ref: any) => {
        // ItemAwareElement has no BPMN `name`; id alone resolves the dangling loopData*Ref.
        const placeholder = moddle.create(descriptor, { id: ref.id });
        placeholder.$parent = ref.element;
        ref.element.set(ref.property, placeholder);
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

    // Keep 'M8flow Connectors' open across panel rebuilds triggered by elements.changed.
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
        attributeFilter: ['class'],
      });
    }

    const onPanelClick = (e: Event) => {
      if (isRestoring) return;
      const target = e.target as HTMLElement | null;
      if (!target || !propertiesPanelParent) return;

      const serviceGroup = propertiesPanelParent.querySelector<HTMLElement>(
        '.bio-properties-panel-group[data-group-id="group-service_task_properties"]',
      );
      const serviceHeader = serviceGroup?.querySelector<HTMLElement>(
        ':scope > .bio-properties-panel-group-header',
      );

      if (serviceHeader && (serviceHeader === target || serviceHeader.contains(target))) {
        // User clicked the header — allow manual close
        openGroupSnapshotRef.current = [];
        keepServiceGroupOpenUntilRef.current = 0;
        return;
      }

      if (serviceGroup && isGroupOpen(serviceGroup)) {
        openGroupSnapshotRef.current = ['group-service_task_properties'];
        keepServiceGroupOpenUntilRef.current = Date.now() + 3000;
      }
    };
    if (propertiesPanelParent) {
      propertiesPanelParent.addEventListener('click', onPanelClick, true);
    }

    let diagramModeler: any = null;
    if (diagramType === 'bpmn') {
      diagramModeler = new BpmnModeler({
        container: '#canvas',
        keyboard: { bindTo: document },
        propertiesPanel: { parent: `#${panelId}` },
        additionalModules: [
          spiffworkflow,
          m8flowExternalForm,
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

    // Badge a task that carries a spiffworkflow pre/post script with a small script
    // icon overlay (pre on the lower-left, post on the lower-right).
    const SCRIPT_BADGES: Array<[string, Record<string, number>]> = [
      ['spiffworkflow:PreScript', { bottom: 25, left: 0 }],
      ['spiffworkflow:PostScript', { bottom: 25, right: 25 }],
    ];

    function createPrePostScriptOverlay(event: any) {
      const element = event.element;
      if (!element || element.type === 'bpmn:ScriptTask') return;

      const extensions = element.businessObject.extensionElements?.values ?? [];
      const overlays = diagramModeler.get('overlays');
      const scriptIcon = convertSvgElementToHtmlString(
        React.createElement(BpmnJsScriptIcon, null),
      );

      SCRIPT_BADGES.forEach(([extensionType, position]) => {
        const script = extensions.find((ext: any) => ext.$type === extensionType);
        if (script?.value) {
          overlays.add(element.id, { position, html: scriptIcon });
        }
      });
    }

    setDiagramModelerState(diagramModeler);

    // Wire the bpmn-js / bpmn-js-spiffworkflow extension events. Registered from a table
    // (not a repeated ladder of .on() calls) so the mapping is data, not boilerplate.
    // The event names are the library's API; the listeners forward to m8flow callbacks.

    // Editor-launch events carry {error, ...}; surface the error then run the launcher.
    const onEditEvent = (launch: (event: any) => void) => (event: any) => {
      if (event.error) console.error(event.error);
      launch(event);
    };

    const listeners: Array<[string, (event: any) => void]> = [
      [
        'spiff.task_metadata_keys.requested',
        (event) =>
          event.eventBus.fire('spiff.task_metadata_keys.returned', {
            keys: TASK_METADATA,
          }),
      ],
      [
        'spiff.script.edit',
        onEditEvent((e) =>
          handleLaunchScriptEditor(e.element, e.script, e.scriptType, e.eventBus),
        ),
      ],
      [
        'spiff.markdown.edit',
        onEditEvent((e) => handleLaunchMarkdownEditor(e.element, e.value, e.eventBus)),
      ],
      [
        'spiff.file.edit',
        onEditEvent((e) =>
          callbacksRef.current.onLaunchJsonSchemaEditor?.(e.element, e.value, e.eventBus),
        ),
      ],
      [
        'spiff.callactivity.edit',
        (e) => callbacksRef.current.onLaunchBpmnEditor?.(e.processId),
      ],
      ['spiff.dmn.edit', (e) => callbacksRef.current.onLaunchDmnEditor?.(e.value)],
      ['element.click', handleElementClick],
      [
        'elements.changed',
        (event) => {
          // Snapshot the open property groups before the panel rebuilds, so the
          // MutationObserver can restore them afterwards.
          if (getOpenGroupIds().includes('group-service_task_properties')) {
            openGroupSnapshotRef.current = ['group-service_task_properties'];
            keepServiceGroupOpenUntilRef.current = Date.now() + 3000;
          }
          callbacksRef.current.onElementsChanged?.(event);
        },
      ],
      ['spiff.service_tasks.requested', handleServiceTasksRequested],
      ['spiff.data_stores.requested', handleDataStoresRequested],
      [
        'spiff.json_schema_files.requested',
        (event) => {
          callbacksRef.current.onJsonSchemaFilesRequested?.(event);
          handleServiceTasksRequested(event);
        },
      ],
      ['spiff.dmn_files.requested', (e) => callbacksRef.current.onDmnFilesRequested?.(e)],
      ['spiff.messages.requested', (e) => callbacksRef.current.onMessagesRequested?.(e)],
    ];

    // Edit-mode only: script-task pre/post overlays.
    if (diagramType !== 'readonly') {
      listeners.push(['shape.added', (event) => createPrePostScriptOverlay(event)]);
    }

    listeners.forEach(([eventName, listener]) => diagramModeler.on(eventName, listener));

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