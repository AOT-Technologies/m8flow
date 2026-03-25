/**
 * A base viewer for BPMN 2.0 diagrams.
 *
 * Have a look at {@link bpmn-js/lib/Viewer}, {@link bpmn-js/lib/NavigatedViewer} or {@link bpmn-js/lib/Modeler} for
 * bundles that include actual features.
 *
 *
 * @extends Diagram<ServiceMap>
 *
 */
export default class BaseViewer<ServiceMap = null> extends Diagram<ServiceMap> {
  /**
   * @param options The options to configure the viewer.
   */
  constructor(options?: BaseViewerOptions);

  /**
   * Parse and render a BPMN 2.0 diagram.
   *
   * Once finished the viewer reports back the result to the
   * provided callback function with (err, warnings).
   *
   * ## Life-Cycle Events
   *
   * During import the viewer will fire life-cycle events:
   *
   *   * import.parse.start (about to read model from XML)
   *   * import.parse.complete (model read; may have worked or not)
   *   * import.render.start (graphical import start)
   *   * import.render.complete (graphical import finished)
   *   * import.done (everything done)
   *
   * You can use these events to hook into the life-cycle.
   *
   * @throws {ImportXMLError} An error thrown during the import of the XML.
   *
   * @fires BaseViewer#ImportParseStartEvent
   * @fires BaseViewer#ImportParseCompleteEvent
   * @fires Importer#ImportRenderStartEvent
   * @fires Importer#ImportRenderCompleteEvent
   * @fires BaseViewer#ImportDoneEvent
   *
   * @param xml The BPMN 2.0 XML to be imported.
   * @param bpmnDiagram The optional diagram or Id of the BPMN diagram to open.
   *
   * @return A promise resolving with warnings that were produced during the import.
   */
  importXML(xml: string, bpmnDiagram?: ModdleElement | string): Promise<ImportXMLResult>;

  /**
   * Import parsed definitions and render a BPMN 2.0 diagram.
   *
   * Once finished the viewer reports back the result to the
   * provided callback function with (err, warnings).
   *
   * ## Life-Cycle Events
   *
   * During import the viewer will fire life-cycle events:
   *
   *   * import.render.start (graphical import start)
   *   * import.render.complete (graphical import finished)
   *
   * You can use these events to hook into the life-cycle.
   *
   * @throws {ImportDefinitionsError} An error thrown during the import of the definitions.
   *
   * @param definitions The definitions.
   * @param bpmnDiagram The optional diagram or ID of the BPMN diagram to open.
   *
   * @return A promise resolving with warnings that were produced during the import.
   */
  importDefinitions(definitions: ModdleElement, bpmnDiagram?: ModdleElement | string): Promise<ImportDefinitionsResult>;

  /**
   * Open diagram of previously imported XML.
   *
   * Once finished the viewer reports back the result to the
   * provided callback function with (err, warnings).
   *
   * ## Life-Cycle Events
   *
   * During switch the viewer will fire life-cycle events:
   *
   *   * import.render.start (graphical import start)
   *   * import.render.complete (graphical import finished)
   *
   * You can use these events to hook into the life-cycle.
   *
   * @throws {OpenError} An error thrown during opening.
   *
   * @param bpmnDiagramOrId The diagram or Id of the BPMN diagram to open.
   *
   * @return A promise resolving with warnings that were produced during opening.
   */
  open(bpmnDiagramOrId: ModdleElement | string): Promise<OpenResult>;

  /**
   * Export the currently displayed BPMN 2.0 diagram as
   * a BPMN 2.0 XML document.
   *
   * ## Life-Cycle Events
   *
   * During XML saving the viewer will fire life-cycle events:
   *
   *   * saveXML.start (before serialization)
   *   * saveXML.serialized (after xml generation)
   *   * saveXML.done (everything done)
   *
   * You can use these events to hook into the life-cycle.
   *
   * @throws {Error} An error thrown during export.
   *
   * @fires BaseViewer#SaveXMLStart
   * @fires BaseViewer#SaveXMLDone
   *
   * @param options The options.
   *
   * @return A promise resolving with the XML.
   */
  saveXML(options?: SaveXMLOptions): Promise<SaveXMLResult>;

  /**
   * Export the currently displayed BPMN 2.0 diagram as
   * an SVG image.
   *
   * ## Life-Cycle Events
   *
   * During SVG saving the viewer will fire life-cycle events:
   *
   *   * saveSVG.start (before serialization)
   *   * saveSVG.done (everything done)
   *
   * You can use these events to hook into the life-cycle.
   *
   * @throws {Error} An error thrown during export.
   *
   * @fires BaseViewer#SaveSVGDone
   *
   * @return A promise resolving with the SVG.
   */
  saveSVG(): Promise<SaveSVGResult>;

  /**
   * Return modules to instantiate with.
   *
   * @return The modules.
   */
  getModules(): ModuleDeclaration[];

  /**
   * Register an event listener for events with the given name.
   *
   * The callback will be invoked with `event, ...additionalArguments`
   * that have been passed to {@link EventBus#fire}.
   *
   * Returning false from a listener will prevent the events default action
   * (if any is specified). To stop an event from being processed further in
   * other listeners execute {@link Event#stopPropagation}.
   *
   * Returning anything but `undefined` from a listener will stop the listener propagation.
   *
   *
   * @param events to subscribe to
   * @param callback
   * @param that callback context
   */
  on<EventName extends keyof EventMap<ServiceMap>>(
    events: EventName,
    callback: EventBusEventCallback<(EventMap<ServiceMap>)[EventName]>,
    that?: any
  ): void;

  /**
   * Register an event listener for events with the given name.
   *
   * The callback will be invoked with `event, ...additionalArguments`
   * that have been passed to {@link EventBus#fire}.
   *
   * Returning false from a listener will prevent the events default action
   * (if any is specified). To stop an event from being processed further in
   * other listeners execute {@link Event#stopPropagation}.
   *
   * Returning anything but `undefined` from a listener will stop the listener propagation.
   *
   *
   * @param events to subscribe to
   * @param priority listen priority
   * @param callback
   * @param that callback context
   */
  on<EventName extends keyof EventMap<ServiceMap>>(
    events: EventName,
    priority: number,
    callback: EventBusEventCallback<(EventMap<ServiceMap>)[EventName]>,
    that?: any
  ): void;

  /**
   *
   * Register an event listener for events with the given name.
   *
   * The callback will be invoked with `event, ...additionalArguments`
   * that have been passed to {@link EventBus#fire}.
   *
   * Returning false from a listener will prevent the events default action
   * (if any is specified). To stop an event from being processed further in
   * other listeners execute {@link Event#stopPropagation}.
   *
   * Returning anything but `undefined` from a listener will stop the listener propagation.
   *
   *
   * @param events The event(s) to listen to.
   * @param callback The callback.
   * @param that Value of `this` the callback will be called with.
   */
  on<T>(events: string|string[], callback: EventBusEventCallback<T>, that?: any): void;

  /**
   *
   * Register an event listener for events with the given name.
   *
   * The callback will be invoked with `event, ...additionalArguments`
   * that have been passed to {@link EventBus#fire}.
   *
   * Returning false from a listener will prevent the events default action
   * (if any is specified). To stop an event from being processed further in
   * other listeners execute {@link Event#stopPropagation}.
   *
   * Returning anything but `undefined` from a listener will stop the listener propagation.
   *
   *
   * @param events The event(s) to listen to.
   * @param priority The priority with which to listen.
   * @param callback The callback.
   * @param that Value of `this` the callback will be called with.
   */
  on<T>(
    events: string|string[],
    priority: number,
    callback: EventBusEventCallback<T>,
    that?: any
  ): void;

  /**
   * Remove an event listener.
   *
   * @param events The event(s).
   * @param callback The callback.
   */
  off(events: string | string[], callback?: Function): void;

  /**
   * Attach the viewer to an HTML element.
   *
   * @param parentNode The parent node to attach to.
   */
  attachTo(parentNode: HTMLElement): void;

  /**
   * Get the definitions model element.
   *
   * @return The definitions model element.
   */
  getDefinitions(): ModdleElement;

  /**
   * Detach the viewer.
   *
   * @fires BaseViewer#DetachEvent
   */
  detach(): void;
}

type EventBus<T> = import('diagram-js/lib/core/EventBus').default<T>;
type EventBusEventCallback<T> = import('diagram-js/lib/core/EventBus').EventBusEventCallback<T>;
type ModuleDeclaration = import('didi').ModuleDeclaration;
type Moddle = import('./model/Types').Moddle;
type ModdleElement = import('./model/Types').ModdleElement;
type ModdleExtension = import('./model/Types').ModdleExtension;

export type BaseViewerOptions = {
    width?: number | string;
    height?: number | string;
    position?: string;
    container?: string | HTMLElement;
    moddleExtensions?: ModdleExtensions;
    additionalModules?: ModuleDeclaration[];
} & Record<string, any>;

export type ModdleElementsById = Record<string, ModdleElement>;

export type ModdleExtensions = {
    [key: string]: import("./model/Types").ModdleExtension;
};

export type ImportXMLResult = {
    warnings: string[];
};

export type ImportXMLError = ImportXMLResult & Error;
export type ImportDefinitionsResult = ImportXMLResult;
export type ImportDefinitionsError = ImportXMLError;
export type OpenResult = ImportXMLResult;
export type OpenError = ImportXMLError;

export type SaveXMLOptions = {
    format?: boolean;
    preamble?: boolean;
};

export type SaveXMLResult = {
    xml?: string;
    error?: Error;
};

export type SaveSVGResult = {
    svg: string;
};

export type ImportParseStartEvent = {
    xml: string;
};

export type ImportParseCompleteEvent = {
    error?: ImportXMLError;
    definitions?: ModdleElement;
    elementsById?: ModdleElementsById;
    references?: ModdleElement[];
    warnings: string[];
};

export type ImportDoneEvent = {
    error?: ImportXMLError;
    warnings: string[];
};

export type SaveXMLStartEvent = {
    definitions: ModdleElement;
};

export type SaveXMLDoneEvent = SaveXMLResult;

export type SaveSVGDoneEvent = {
    error?: Error;
    svg: string;
};

export type EventMap<Type> = Type extends {
    eventBus: import("diagram-js/lib/core/EventBus").default<infer X>;
} ? X : never;

import Diagram from 'diagram-js';
