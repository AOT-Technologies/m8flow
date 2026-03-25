/**
 * Creates a new bpmn:CategoryValue inside a new bpmn:Category
 *
 * @param bpmnFactory
 *
 * @return
 */
export function createCategory(bpmnFactory: BpmnFactory): any;

/**
 * Creates a new bpmn:CategoryValue inside a new bpmn:Category
 *
 * @param bpmnFactory
 *
 * @return
 */
export function createCategoryValue(bpmnFactory: BpmnFactory): any;

/**
 * Adds category value to definitions
 *
 * @param categoryValue
 * @param category
 * @param definitions
 *
 * @return
 */
export function linkCategoryValue(categoryValue: any, category: any, definitions: any): any;

/**
 * Unlink category value from parent
 *
 * @param categoryValue
 *
 * @return
 */
export function unlinkCategoryValue(categoryValue: any): any;

/**
 * Unlink category from parent
 *
 * @param category
 *
 * @return
 */
export function unlinkCategory(category: any): any;

type BpmnFactory = import('../../BpmnFactory').default;
export type ModdleElement = any;
