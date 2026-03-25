export function getPropertyNames(descriptor: any, keepDefaultProperties: any): any[];

/**
 * Utility for copying model properties from source element to target element.
 *
 */
export default class ModdleCopy {
  static $inject: string[];

  /**
   * @param eventBus
   * @param bpmnFactory
   * @param moddle
   */
  constructor(eventBus: EventBus, bpmnFactory: BpmnFactory, moddle: Moddle);

  /**
   * Copy model properties of source element to target element.
   *
   * @param sourceElement
   * @param targetElement
   * @param propertyNames
   * @param clone
   *
   * @return
   */
  copyElement(sourceElement: ModdleElement, targetElement: ModdleElement, propertyNames?: string[], clone?: boolean): ModdleElement;

  /**
   * Copy model property.
   *
   * @param property
   * @param parent
   * @param propertyName
   * @param clone
   *
   * @return
   */
  copyProperty(property: any, parent: ModdleElement, propertyName: string, clone?: boolean): any;
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnFactory = import('../modeling/BpmnFactory').default;
type Moddle = import('../../model/Types').Moddle;
type ModdleElement = import('../../model/Types').ModdleElement;
