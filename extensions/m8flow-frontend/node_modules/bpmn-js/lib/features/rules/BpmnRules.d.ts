/**
 * BPMN-specific modeling rules.
 *
 */
export default class BpmnRules extends RuleProvider {
    canConnectMessageFlow: typeof canConnectMessageFlow;
    canConnectSequenceFlow: typeof canConnectSequenceFlow;
    canConnectDataAssociation: typeof canConnectDataAssociation;
    canConnectAssociation: typeof canConnectAssociation;
    canConnectCompensationAssociation: typeof canConnectCompensationAssociation;
    canMove: typeof canMove;
    canAttach: typeof canAttach;
    canReplace: typeof canReplace;
    canDrop: typeof canDrop;
    canInsert: typeof canInsert;
    canCreate: typeof canCreate;
    canConnect: typeof canConnect;
    canResize: typeof canResize;
    canCopy: typeof canCopy;
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Connection = import('../../model/Types').Connection;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;
type ModdleElement = import('../../model/Types').ModdleElement;
type Point = import('diagram-js/lib/util/Types').Point;
type Rect = import('diagram-js/lib/util/Types').Rect;

export type CanConnectResult = {
    associationDirection?: 'None' | 'One' | 'Both';
    type: string;
} | boolean | null;

export type CanReplaceResult = {
    id: string;
    type: string;
} | boolean;

import RuleProvider from 'diagram-js/lib/features/rules/RuleProvider';

/**
 * @param source
 * @param target
 *
 * @return
 */
declare function canConnectMessageFlow(source: Element, target: Element): boolean;

/**
 * @param source
 * @param target
 *
 * @return
 */
declare function canConnectSequenceFlow(source: Element, target: Element): boolean;

/**
 * @param source
 * @param target
 *
 * @return
 */
declare function canConnectDataAssociation(source: Element, target: Element): CanConnectResult;

/**
 * @param source
 * @param target
 *
 * @return
 */
declare function canConnectAssociation(source: Element, target: Element): CanConnectResult;

/**
 * @param source
 * @param target
 *
 * @return
 */
declare function canConnectCompensationAssociation(source: Element, target: Element): boolean;

/**
 * @param elements
 * @param target
 *
 * @return
 */
declare function canMove(elements: Element[], target: Shape): boolean;

/**
 * TODO(philippfromme): remove `source` parameter
 *
 * @param elements
 * @param target
 * @param source
 * @param position
 *
 * @return
 */
declare function canAttach(elements: Element[], target: Shape, source: Element, position?: Point): boolean | 'attach';

/**
 * Check whether the given elements can be replaced. Return all elements which
 * can be replaced.
 *
 * @example
 *
 * ```javascript
 * [{
 *   id: 'IntermediateEvent_1',
 *   type: 'bpmn:StartEvent'
 * },
 * {
 *   id: 'Task_1',
 *   type: 'bpmn:ServiceTask'
 * }]
 * ```
 *
 * @param  elements
 * @param  target
 * @param  position
 *
 * @return
 */
declare function canReplace(elements: Element[], target?: Shape, position?: Point): CanReplaceResult;

/**
 * Can an element be dropped into the target element.
 *
 * @param element
 * @param target
 *
 * @return
 */
declare function canDrop(element: Element, target: Shape): boolean;

/**
 * @param shape
 * @param connection
 * @param position
 *
 * @return
 */
declare function canInsert(shape: Shape, connection: Connection, position: Point): boolean;

/**
 * @param shape
 * @param target
 * @param source
 * @param position
 *
 * @return
 */
declare function canCreate(shape: Shape, target: Shape, source: Element, position: Point): boolean;

/**
 * @param source
 * @param target
 * @param connection
 *
 * @return
 */
declare function canConnect(source: Element, target: Element, connection: Connection): CanConnectResult;

/**
 * @param shape
 * @param newBounds
 *
 * @return
 */
declare function canResize(shape: Shape, newBounds: Rect): boolean;

/**
 * @param elements
 * @param element
 *
 * @return
 */
declare function canCopy(elements: Element[], element: Element): boolean;

export {};
