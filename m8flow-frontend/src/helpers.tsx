/**
 * M8flow Extensions - Helpers Override
 *
 * This file re-exports all helpers from the core SpiffWorkflow frontend
 * and overrides specific functions with M8flow-specific implementations.
 */

// Re-export everything from the core helpers
export {
  DEFAULT_PER_PAGE,
  DEFAULT_PAGE,
  doNothing,
  matchNumberRegex,
  slugifyString,
  HUMAN_TASK_TYPES,
  MULTI_INSTANCE_TASK_TYPES,
  LOOP_TASK_TYPES,
  underscorizeString,
  getKeyByValue,
  recursivelyChangeNullAndUndefined,
  selectKeysFromSearchParams,
  capitalizeFirstLetter,
  titleizeString,
  objectIsEmpty,
  getPageInfoFromSearchParams,
  makeid,
  getProcessModelFullIdentifierFromSearchParams,
  truncateString,
  pathFromFullUrl,
  modifyProcessIdentifierForPathParam,
  unModifyProcessIdentifierForPathParam,
  getGroupFromModifiedModelId,
  splitProcessModelId,
  refreshAtInterval,
  getBpmnProcessIdentifiers,
  isANumber,
  getProcessStatus,
  getLastMilestoneFromProcessInstance,
  parseTaskShowUrl,
  isURL,
  renderElementsForArray,
  convertSvgElementToHtmlString,
} from "@spiffworkflow-frontend/helpers";

/**
 * Sets the page title with M8flow branding
 * This overrides the default SpiffWorkflow setPageTitle function
 * @param items - Array of strings to append to the page title
 */
export const setPageTitle = (items: Array<string>) => {
  document.title = ["M8flow"].concat(items || []).join(" - ");
};
