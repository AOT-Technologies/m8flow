/**
 * @type {ReplaceOption[]}
 */
export const START_EVENT: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const START_EVENT_SUB_PROCESS: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const INTERMEDIATE_EVENT: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const END_EVENT: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const GATEWAY: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const SUBPROCESS_EXPANDED: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const TRANSACTION: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const EVENT_SUB_PROCESS: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const TASK: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const DATA_OBJECT_REFERENCE: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const DATA_STORE_REFERENCE: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const BOUNDARY_EVENT: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const EVENT_SUB_PROCESS_START_EVENT: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const SEQUENCE_FLOW: ReplaceOption[];
/**
 * @type {ReplaceOption[]}
 */
export const PARTICIPANT: ReplaceOption[];
export type LabelGetter = () => string;
export type ReplaceOption = {
    label: string | LabelGetter;
    actionName: string;
    className: string;
    target?: {
        type: string;
        isExpanded?: boolean;
        isInterrupting?: boolean;
        triggeredByEvent?: boolean;
        cancelActivity?: boolean;
        eventDefinitionType?: string;
        eventDefinitionAttrs?: Record<string, any>;
    };
};
