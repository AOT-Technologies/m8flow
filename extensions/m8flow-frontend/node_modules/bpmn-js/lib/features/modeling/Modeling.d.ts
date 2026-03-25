/**
 * The BPMN 2.0 modeling entry point.
 *
 *
 * @extends {BaseModeling<T, U, V, W, X>}
 *
 */
export default class Modeling<T extends import("../../model/Types").Connection = import("../../model/Types").Connection, U extends import("../../model/Types").Element = import("../../model/Types").Element, V extends import("../../model/Types").Label = import("../../model/Types").Label, W extends import("../../model/Types").Parent = import("../../model/Types").Parent, X extends import("../../model/Types").Shape = import("../../model/Types").Shape> extends BaseModeling<T, U, V, W, X> {
  /**
   * @param eventBus
   * @param elementFactory
   * @param commandStack
   * @param bpmnRules
   */
  constructor(eventBus: EventBus, elementFactory: ElementFactory, commandStack: CommandStack, bpmnRules: BpmnRules);

  getHandlers(): any;

  /**
   * Update an element's label.
   *
   * @param element The element.
   * @param newLabel The new label.
   * @param newBounds The optional bounds of the label.
   * @param hints The optional hints.
   */
  updateLabel(element: Element, newLabel: string, newBounds?: Rect, hints?: UpdateLabelHints): void;

  /**
   * @param source
   * @param target
   * @param attrs
   * @param hints
   *
   * @return
   */
  connect(source: Element, target: Element, attrs?: Partial<Connection>, hints?: ModelingHints): T;

  /**
   * Update a model element's properties.
   *
   * @param element The element.
   * @param moddleElement The model element.
   * @param properties The updated properties.
   */
  updateModdleProperties(element: Element, moddleElement: ModdleElement, properties: any): void;

  /**
   * Update an element's properties.
   *
   * @param element The element.
   * @param properties The updated properties.
   */
  updateProperties(element: Element, properties: any): void;

  /**
   * Resize a lane.
   *
   * @param laneShape The lane.
   * @param newBounds The new bounds of the lane.
   * @param balanced Wether to resize neighboring lanes.
   */
  resizeLane(laneShape: Shape, newBounds: Rect, balanced?: boolean): void;

  /**
   * Add a lane.
   *
   * @param targetLaneShape The shape to add the lane to.
   * @param location The location.
   *
   * @return The added lane.
   */
  addLane(targetLaneShape: Shape, location: string): Shape;

  /**
   * Split a lane.
   *
   * @param targetLane The lane to split.
   * @param count The number of lanes to split the lane into. Must not
   * exceed the number of existing lanes.
   */
  splitLane(targetLane: Shape, count: number): void;

  /**
   * Turn a process into a collaboration.
   *
   * @return The root of the collaboration.
   */
  makeCollaboration(): Root;

  /**
   * Transform a collaboration into a process.
   *
   * @return The root of the process.
   */
  makeProcess(): Root;

  /**
   * Update the referenced lanes of each flow node.
   *
   * @param flowNodeShapes The flow nodes to update.
   * @param laneShapes The lanes.
   */
  updateLaneRefs(flowNodeShapes: Shape[], laneShapes: Shape[]): void;

  /**
   * Claim an ID.
   *
   * @param id The ID to claim.
   * @param moddleElement The model element the ID is claimed for.
   */
  claimId(id: string, moddleElement: ModdleElement): void;

  /**
   * Unclaim an ID.
   *
   * @param id The ID to unclaim.
   * @param moddleElement The model element the ID is claimed for.
   */
  unclaimId(id: string, moddleElement: ModdleElement): void;

  /**
   * Set the color(s) of one or many elements.
   *
   * @param elements The elements to set the color(s) for.
   * @param colors The color(s) to set.
   */
  setColor(elements: Element[], colors: Colors): void;
}

type BpmnRules = import('../rules/BpmnRules').default;
type CommandStack = import('diagram-js/lib/command/CommandStack').default;
type ElementFactory = import('./ElementFactory').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type ModelingHints = import('diagram-js/lib/features/modeling/Modeling').ModelingHints;
type Connection = import('../../model/Types').Connection;
type Element = import('../../model/Types').Element;
type Label = import('../../model/Types').Label;
type Parent = import('../../model/Types').Parent;
type Root = import('../../model/Types').Root;
type Shape = import('../../model/Types').Shape;
type ModdleElement = import('../../model/Types').ModdleElement;
type Rect = import('diagram-js/lib/util/Types').Rect;
type Colors = import('../../util/Types').Colors;

export type UpdateLabelHints = {
    removeShape?: boolean;
};

import BaseModeling from 'diagram-js/lib/features/modeling/Modeling';
