'use strict';

Object.defineProperty(exports, '__esModule', { value: true });

var minDash = require('min-dash');

/**
 * Get a inputOutput from the business object
 *
 * @param {ModdleElement} element
 *
 * @return {ModdleElement} the inputOutput object
 */
function getInputOutput(element) {
  return (getElements(element, 'camunda:InputOutput') || [])[0];
}

/**
 * Return all input parameters existing in the business object, and
 * an empty array if none exist.
 *
 * @param  {ModdleElement} element
 *
 * @return {Array<ModdleElement>} a list of input parameter objects
 */
function getInputParameters(element) {
  return getParameters(element, 'inputParameters');
}

/**
 * Return all output parameters existing in the business object, and
 * an empty array if none exist.
 *
 * @param  {ModdleElement} element
 * @param  {boolean} insideConnector
 *
 * @return {Array<ModdleElement>} a list of output parameter objects
 */
function getOutputParameters(element) {
  return getParameters(element, 'outputParameters');
}

/**
 * Return all form fields existing in the business object, and
 * an empty array if none exist.
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>} a list of form fields
 */
function getFormFields(element) {
  var formData = getFormData(element);
  return (formData && formData.get('fields')) || [];
}

/**
 * Return form data existing in the business object
 *
 * @param {ModdleElement} element
 *
 * @return {ModdleElement}
 */
function getFormData(element) {
  return getElements(element, 'camunda:FormData')[0];
}

/**
 * Return out mappings existing in the business object
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>}
 */
function getOutMappings(element) {
  return getElements(element, 'camunda:Out');
}


// helpers //////////

function getElements(element, type, property) {
  var elements = getExtensionElements(element, type);

  return !property ? elements : (elements[0] || {})[property] || [];
}

function getParameters(element, property) {
  var inputOutput = getInputOutput(element);

  return (inputOutput && inputOutput.get(property)) || [];
}

function getExtensionElements(element, type) {
  var elements = [];
  var extensionElements = element.get('extensionElements');

  if (typeof extensionElements !== 'undefined') {
    var extensionValues = extensionElements.get('values');

    if (typeof extensionValues !== 'undefined') {
      elements = minDash.filter(extensionValues, function(value) {
        return is$2(value, type);
      });
    }
  }

  return elements;
}

function is$2(element, type) {
  return (
    element &&
    typeof element.$instanceOf === 'function' &&
    element.$instanceOf(type)
  );
}

/**
 * Get all parent elements for a given element.
 *
 * @param {ModdleElement|string} element
 *
 * @returns {Array<ModdleElement>}
 */
function getParents(element) {
  var parents = [];
  var current = element;

  while (current.$parent) {
    parents.push(current.$parent);
    current = current.$parent;
  }

  return parents;
}

/**
 * Iterate over each element in a collection, calling the iterator function `fn`
 * with (element, index, recursionDepth).
 *
 * Recurse into all elements that are returned by `fn`.
 *
 * @param  {Object|Array<Object>} elements
 * @param  {Function} fn iterator function called with (element, index, recursionDepth)
 * @param  {number} [depth] maximum recursion depth
 */
function eachElement(elements, fn, depth) {
  depth = depth || 0;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(s, i) {
    var filter = fn(s, i, depth);

    if (minDash.isArray(filter) && filter.length) {
      eachElement(filter, fn, depth + 1);
    }
  });
}

/**
 * Adds an element to a collection and returns true if the
 * element was added.
 *
 * @param {Array<Object>} elements
 * @param {Object} e
 * @param {boolean} unique
 */
function add(elements, e, unique) {
  var canAdd = !unique || elements.indexOf(e) === -1;

  if (canAdd) {
    elements.push(e);
  }

  return canAdd;
}

/**
 * Collects self + flow elements up to a given depth from a list of elements.
 *
 * @param  {ModdleElement|Array<ModdleElement>} elements the elements to select the flowElements from
 * @param  {boolean} unique whether to return a unique result set (no duplicates)
 * @param  {number} maxDepth the depth to search through or -1 for infinite
 *
 * @return {Array<ModdleElement>} found elements
 */
function selfAndFlowElements(elements, unique, maxDepth) {
  var result = [],
      processedFlowElements = [];

  eachElement(elements, function(element, i, depth) {
    add(result, element, unique);

    var flowElements = element.flowElements;

    // max traversal depth not reached yet
    if (maxDepth === -1 || depth < maxDepth) {

      // flowElements exist && flowElements not yet processed
      if (flowElements && add(processedFlowElements, flowElements, unique)) {
        return flowElements;
      }
    }
  });

  return result;
}

/**
 * Return self + ALL flowElements for a number of elements
 *
 * @param  {Array<ModdleElement>} elements to query
 * @param  {boolean} allowDuplicates to allow duplicates in the result set
 *
 * @return {Array<ModdleElement>} the collected elements
 */
function selfAndAllFlowElements(elements, allowDuplicates) {
  return selfAndFlowElements(elements, !allowDuplicates, -1);
}

/**
 * Return full moddle element for given element id
 *
 * @param {string} elementId
 * @param {ModdleElement} rootElement
 *
 * @returns {ModdleElement}
 */
function getElement(elementId, rootElement) {
  var allElements = selfAndAllFlowElements(rootElement);

  return minDash.find(allElements, function(element) {
    return element.id === elementId;
  });
}

function addVariableToList(variablesList, newVariable) {
  var foundIdx = minDash.findIndex(variablesList, function(variable) {
    return (
      variable.name === newVariable.name && variable.scope === newVariable.scope
    );
  });

  if (foundIdx >= 0) {
    variablesList[foundIdx].origin = combineArrays$1(
      variablesList[foundIdx].origin,
      newVariable.origin
    );
  } else {
    variablesList.push(newVariable);
  }
}

/**
 * Creates new process variable definition object
 * Identifies correct (highest) scope, in which variable is available
 *
 * @param {ModdleElement} flowElement
 * @param {String} name
 * @param {ModdleElement} defaultScope
 *
 * @returns {ProcessVariable}
 */
function createProcessVariable(flowElement, name, defaultScope) {
  var scope = getScope(flowElement, defaultScope, name);

  return {
    name: name,
    origin: [ flowElement ],
    scope: scope,
  };
}


// helpers ////////////////////

/**
 * Set parent container if it defines it's own scope for the variable, so
 * when it defines an input mapping for it. Otherwise returns the default global scope
 */
function getScope(element, globalScope, variableName) {
  var parents = getParents(element);

  var scopedParent = minDash.find(parents, function(parent) {
    return (
      is$1(parent, 'bpmn:SubProcess') && hasInputParameter(parent, variableName)
    );
  });

  return scopedParent ? scopedParent : globalScope;
}

function is$1(element, type) {
  return (
    element &&
      typeof element.$instanceOf === 'function' &&
      element.$instanceOf(type)
  );
}

function hasInputParameter(element, name) {
  return minDash.find(getInputParameters(element), function(input) {
    return input.name === name;
  });
}

function combineArrays$1(a, b) {
  return a.concat(b);
}

/**
 * Retrieves process variables defined in output parameters, e.g.
 *
 * <camunda:inputOutput>
 *   <camunda:outputParameter name="variable1">200</camunda:outputParameter>
 *   <camunda:outputParameter name="variable2">${myLocalVar + 20}</camunda:outputParameter>
 * </camunda:inputOutput>
 *
 * => Adds two variables "variable1" & "variable2" to the list.
 *
 */
function extractOutputParameters(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    // variables are created by output parameters
    var outputParameters = getOutputParameters(element);

    // extract all variables with correct scope
    minDash.forEach(outputParameters, function(parameter) {
      var newVariable = createProcessVariable(
        element,
        parameter.name,
        containerElement
      );

      addVariableToList(processVariables, newVariable);
    });
  });

  return processVariables;
}

/**
 * Retrieves process variables defined in result variables, e.g.
 *
 * <bpmn:sendTask
 *   id="SendTask_1"
 *   camunda:expression="${myBean.ready}"
 *   camunda:resultVariable="variable1"
 * />
 *
 * => Adds one variable "variable1"to the list.
 *
 */
function extractResultVariables(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var resultVariable = getResultVariable(element);

    if (resultVariable) {
      var newVariable = createProcessVariable(
        element,
        resultVariable,
        containerElement
      );

      addVariableToList(processVariables, newVariable);
    }
  });

  return processVariables;
}


// helpers ///////////////////////

function getResultVariable(element) {
  return element.get('camunda:resultVariable');
}

/**
 * Retrieves process variables defined in form fields, e.g.
 *
 * <camunda:formData>
 *   <camunda:formField id="variable1" />
 *   <camunda:formField id="variable2" />
 * </camunda:formData>
 *
 * => Adds two variables "variable1" & "variable2" to the list.
 *
 */
function extractFormFields(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var formFields = getFormFields(element);

    // extract all variables with correct scope
    minDash.forEach(formFields, function(field) {
      var newVariable = createProcessVariable(
        element,
        field.id,
        containerElement
      );

      addVariableToList(processVariables, newVariable);
    });
  });

  return processVariables;
}

/**
 * Retrieves process variables defined in output mappings and
 * ignores local variables, e.g.
 *
 * <bpmn:extensionElements>
 *   <camunda:out sourceExpression="${myBean.ready}" target="variable1" />
 *   <camunda:out source="foo" target="variableLocal" local="true" />
 * </bpmn:extensionElements>
 *
 * => Adds one variable "variable1" to the list.
 *
 */
function extractOutMappings(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var outMappings = getOutMappings(element);

    // extract all variables with correct scope
    minDash.forEach(outMappings, function(mapping) {

      // do not use variables marked as <local>
      if (mapping.local) {
        return;
      }

      var newVariable = createProcessVariable(
        element,
        mapping.target,
        containerElement
      );

      addVariableToList(processVariables, newVariable);
    });
  });

  return processVariables;
}

/**
 *
 * @param {ModdleElement} element
 * @param {string} [type] - optional
 *
 * @return {Array<ModdleElement>|undefined} collection of event definitions or none
 */
function getEventDefinitions(element, type) {
  var eventDefinitions = element.eventDefinitions;

  if (!eventDefinitions || !type) {
    return eventDefinitions;
  }

  return minDash.filter(eventDefinitions, function(definition) {
    return is(definition, type);
  });
}

/**
 * Returns error event definitions for a given element.
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>} collection of error event definitions
 */
function getErrorEventDefinitions(element) {
  return getEventDefinitions(element, 'bpmn:ErrorEventDefinition');
}

/**
 * Returns escalation event definitions for a given element.
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>} collection of escalation event definitions
 */
function getEscalationEventDefinitions(element) {
  return getEventDefinitions(element, 'bpmn:EscalationEventDefinition');
}


// helper ////////////////

function is(element, type) {
  return (
    element &&
    typeof element.$instanceOf === 'function' &&
    element.$instanceOf(type)
  );
}

/**
 * Retrieves process variables defined in event definitions, e.g.
 *
 * <bpmn:escalationEventDefinition
 *   id="EscalationEventDefinition_1"
 *   escalationRef="Escalation_1"
 *   camunda:escalationCodeVariable="variable1"
 * />
 *
 * => Adds one variable "variable1" to the list.
 *
 * <bpmn:errorEventDefinition
 *   id="ErrorEventDefinition_1"
 *   errorRef="Error_1"
 *   camunda:errorCodeVariable="variable2"
 *   camunda:errorMessageVariable="variable3"
 * />
 *
 * => Adds two variables "variable2" & "variable3" to the list.
 *
 */
function extractEventDefinitionVariables(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  var addVariable = function(element, name) {
    var newVariable = createProcessVariable(
      element,
      name,
      containerElement
    );

    addVariableToList(processVariables, newVariable);
  };

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    // (1) error event code + message variable
    var errorEventDefinitions = getErrorEventDefinitions(element);

    minDash.forEach(errorEventDefinitions, function(definition) {

      var errorCodeVariable = definition.get('errorCodeVariable'),
          errorMessageVariable = definition.get('errorMessageVariable');

      if (errorCodeVariable) {
        addVariable(element, errorCodeVariable);
      }

      if (errorMessageVariable) {
        addVariable(element, errorMessageVariable);
      }
    });

    // (2) escalation code variable
    var escalationEventDefinitions = getEscalationEventDefinitions(element);

    minDash.forEach(escalationEventDefinitions, function(definition) {

      var escalationCodeVariable = definition.get('escalationCodeVariable');

      if (escalationCodeVariable) {
        addVariable(element, escalationCodeVariable);
      }
    });

  });

  return processVariables;
}

var extractors = [
  extractOutputParameters,
  extractResultVariables,
  extractFormFields,
  extractOutMappings,
  extractEventDefinitionVariables
];

/**
 * @typedef {Object} ProcessVariable
 * @property {string} name
 * @property {Array<ModdleElement>} origin
 * @property {ModdleElement} scope
 */


/**
 * Extractors add ProcessVariables to the `options.processVariables` parameter.
 * @callback extractor
 * @param {Object} options
 * @param {Array<ModdleElement>} options.elements
 * @param {ModdleElement} options.containerElement
 * @param {Array<ProcessVariable>} options.processVariables
 */

// api /////////////////////////

/**
 * Retrieves all process variables for a given container element.
 * @param {ModdleElement} containerElement
 * @param {Array<extractor>} additionalExtractors
 *
 * @returns {Promise<Array<ProcessVariable>>}
 */
function getProcessVariables(containerElement, additionalExtractors = []) {
  const allPromises = [];

  var processVariables = [];

  // (1) extract all flow elements inside the container
  var elements = selfAndAllFlowElements([ containerElement ], false);

  // (2) extract all variables from the extractors
  minDash.forEach([ ...extractors, ...additionalExtractors ], function(extractor) {
    allPromises.push(
      extractor({
        elements: elements,
        containerElement: containerElement,
        processVariables: processVariables
      })
    );
  });

  return Promise.all(allPromises)
    .then(() => processVariables);
}

/**
 * Retrieves all variables which are available in the given scope
 *
 * * Exclude variables which are only available in other scopes
 * * Exclude variables which are produced by the given element
 * * Include variables which are available in parent scopes
 *
 * @param {string} scope
 * @param {ModdleElement} rootElement element from where to extract all variables
 * @param {Array<extractor>} additionalExtractors
 *
 * @returns {Promise<Array<ProcessVariable>>}
 */
async function getVariablesForScope(scope, rootElement, additionalExtractors = []) {

  var allVariables = await getProcessVariables(rootElement, additionalExtractors);

  var scopeElement = getElement(scope, rootElement);

  // (1) get variables for given scope
  var scopeVariables = minDash.filter(allVariables, function(variable) {
    return variable.scope.id === scopeElement.id;
  });

  // (2) get variables for parent scopes
  var parents = getParents(scopeElement);

  var parentsScopeVariables = minDash.filter(allVariables, function(variable) {
    return minDash.find(parents, function(parent) {
      return parent.id === variable.scope.id;
    });
  });

  return combineArrays(scopeVariables, parentsScopeVariables);
}

// helpers ////////////////////

function combineArrays(a, b) {
  return a.concat(b);
}

exports.getProcessVariables = getProcessVariables;
exports.getVariablesForScope = getVariablesForScope;
