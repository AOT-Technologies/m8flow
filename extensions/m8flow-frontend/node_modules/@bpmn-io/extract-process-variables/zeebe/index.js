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
  return (getElements(element, 'zeebe:IoMapping') || [])[0];
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
 * Return out mappings existing in the business object
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>}
 */
function getOutMappings(element) {
  return (getInputOutput(element) || {}).outputParameters;
}

/**
 * Return out mappings existing in the business object
 *
 * @param {ModdleElement} element
 *
 * @return {Array<ModdleElement>}
 */
function getInMappings(element) {
  return (getInputOutput(element) || {}).inputParameters;
}

/**
 * Get the inputElement name from a loopCharacteristics
 *
 * @param {MoodleElement} loopCharacteristics
 * @returns {String} outputCollection
 */
function getInputElement(loopCharacteristics) {
  const extensionElement = getElements(loopCharacteristics, 'zeebe:LoopCharacteristics')[0];
  return extensionElement && extensionElement.inputElement;
}

/**
 * Get the outputCollection name from a loopCharacteristics
 *
 * @param {MoodleElement} loopCharacteristics
 * @returns {String} outputCollection
 */
function getOutputCollection(loopCharacteristics) {
  const extensionElement = getElements(loopCharacteristics, 'zeebe:LoopCharacteristics')[0];
  return extensionElement && extensionElement.outputCollection;

}

/**
 * Get a calledDecision from the business object
 *
 * @param {MoodleElement} element
 * @returns {MoodleElement} the calledDecision object
 */
function getCalledDecision(element) {
  return (getElements(element, 'zeebe:CalledDecision') || [])[0];
}


/**
 * Get a script from the business object
 *
 * @param {MoodleElement} element
 * @returns {MoodleElement} the script object
 */
function getScript(element) {
  return (getElements(element, 'zeebe:Script') || [])[0];
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
  var scope = getScope$1(flowElement, defaultScope, name);

  return {
    name: name,
    origin: [ flowElement ],
    scope: scope
  };
}


// helpers ////////////////////

/**
 * Set parent container if it defines it's own scope for the variable, so
 * when it defines an input mapping for it. Otherwise returns the default global scope
 */
function getScope$1(element, globalScope, variableName) {
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
    return input.target === name;
  });
}

function combineArrays$1(a, b) {
  return a.concat(b);
}

/**
 * Retrieves process variables defined in output mappings, e.g.
 *
 * <bpmn:serviceTask id="ServiceTask">
 *   <bpmn:extensionElements>
 *     <zeebe:ioMapping>
 *       <zeebe:input source="= source" target="variable1" />
 *     </zeebe:ioMapping>
 *   </bpmn:extensionElements>
 * </bpmn:serviceTask>
 *
 * => Adds one variable "variable1" to the list.
 *
 */
function extractInMappings(options) {
  var elements = options.elements,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var inMappings = getInMappings(element);

    // extract all variables with correct scope
    minDash.forEach(inMappings, function(mapping) {

      var newVariable = createProcessVariable(
        element,
        mapping.target,
        element
      );

      addVariableToList(processVariables, newVariable);
    });
  });

  return processVariables;
}

/**
 * Retrieves process variables defined in result variables, e.g.
 *
 * <bpmn:serviceTask id="ServiceTask">
 *   <bpmn:multiInstanceLoopCharacteristics>
 *     <bpmn:extensionElements>
 *       <zeebe:loopCharacteristics inputElement="inputElement" outputCollection="outputCollection" />
 *     </bpmn:extensionElements>
 *   </bpmn:multiInstanceLoopCharacteristics>
 * </bpmn:serviceTask>
 *
 * => Adds one variable "inputElement"to the list.
 *
 */
function extractInputElement(options) {
  var elements = options.elements,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var loopCharacteristics = element.loopCharacteristics;

    var inputElement = loopCharacteristics && getInputElement(loopCharacteristics);

    if (inputElement) {
      var newVariable = createProcessVariable(
        element,
        inputElement,
        element
      );

      addVariableToList(processVariables, newVariable);
    }
  });

  return processVariables;
}

/**
 * Retrieves process variables defined in output mappings, e.g.
 *
 * <bpmn:serviceTask id="ServiceTask">
 *   <bpmn:extensionElements>
 *     <zeebe:ioMapping>
 *       <zeebe:output source="= source" target="variable1" />
 *     </zeebe:ioMapping>
 *   </bpmn:extensionElements>
 * </bpmn:serviceTask>
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
 * Retrieves process variables defined in output collection, e.g.
 *
 * <bpmn:serviceTask id="ServiceTask">
 *   <bpmn:multiInstanceLoopCharacteristics>
 *     <bpmn:extensionElements>
 *       <zeebe:loopCharacteristics inputElement="inputElement" outputCollection="outputCollection" />
 *     </bpmn:extensionElements>
 *   </bpmn:multiInstanceLoopCharacteristics>
 * </bpmn:serviceTask>
 *
 * => Adds one variable "outputCollection"to the list.
 *
 */
function extractOutputCollections(options) {
  var elements = options.elements,
      containerElement = options.containerElement,
      processVariables = options.processVariables;

  if (!minDash.isArray(elements)) {
    elements = [ elements ];
  }

  minDash.forEach(elements, function(element) {

    var loopCharacteristics = element.loopCharacteristics;

    var outputCollection = loopCharacteristics && getOutputCollection(loopCharacteristics);

    if (outputCollection) {
      var newVariable = createProcessVariable(
        element,
        outputCollection,
        containerElement
      );

      addVariableToList(processVariables, newVariable);
    }
  });

  return processVariables;
}

/**
 * Retrieves process variables defined in result variables, e.g.
 *
 *   <bpmn:businessRuleTask id="Activity_1">
 *     <bpmn:extensionElements>
 *       <zeebe:calledDecision resultVariable="variable1" />
 *     </bpmn:extensionElements>
 *   </bpmn:businessRuleTask>
 *
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

    var baseElement = getCalledDecision(element) ||
                      getScript(element);

    if (!baseElement) {
      return;
    }

    var resultVariable = baseElement.resultVariable;

    // Checks if output variable exists, the scope gets redefined
    if (processVariables.some(x => x.origin[0] === element && x.scope === containerElement)) {

      // result variable will have local scope
      containerElement = element;

      // check if the output have same name as resultVariable, only proceed with output variable
      if (processVariables.some(variable => variable.name === resultVariable)) {
        return processVariables;
      }

    }

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

var extractors = [
  extractInMappings,
  extractInputElement,
  extractOutMappings,
  extractOutputCollections,
  extractResultVariables
];

/**
 * @typedef {Object} ProcessVariable
 * @property {string} name
 * @property {Array<ModdleElement>} origin
 * @property {ModdleElement} scope
 */

// api /////////////////////////

/**
 * Extractors add ProcessVariables to the `options.processVariables` parameter.
 * @callback extractor
 * @param {Object} options
 * @param {Array<ModdleElement>} options.elements
 * @param {ModdleElement} options.containerElement
 * @param {Array<ProcessVariable>} options.processVariables
 */

/**
 * Retrieves all process variables for a given container element.
 * @param {ModdleElement} containerElement
 * @param {Array<extractor>} [additionalExtractors]
 *
 * @returns {Promise<Array<ProcessVariable>>}
 */
function getProcessVariables(containerElement, additionalExtractors = []) {
  var processVariables = [];

  // (1) extract all flow elements inside the container
  var elements = selfAndAllFlowElements([ containerElement ], false);

  const allPromises = [];

  // (2) extract all variables from the extractors
  minDash.forEach([ ...extractors, ...additionalExtractors ], function(extractor) {
    allPromises.push(extractor({
      elements: elements,
      containerElement: containerElement,
      processVariables: processVariables
    }));
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
 * @param {Array<extractor>} [additionalExtractors]
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


function getVariablesForElement(element, additionalExtractors = []) {
  return getVariablesForScope(getScope(element), getRootElement(element), additionalExtractors);
}

function getScope(element) {
  const bo = getBusinessObject(element);

  if (is(element, 'bpmn:Participant')) {
    return bo.processRef.id;
  }

  return bo.id;
}

function getRootElement(element) {
  const businessObject = getBusinessObject(element);

  if (is(businessObject, 'bpmn:Participant')) {
    return businessObject.processRef;
  }

  if (is(businessObject, 'bpmn:Process')) {
    return businessObject;
  }

  let parent = businessObject;

  while (parent.$parent && !is(parent, 'bpmn:Process')) {
    parent = parent.$parent;
  }

  return parent;
}


// helpers ////////////////////

function combineArrays(a, b) {
  return a.concat(b);
}


function getBusinessObject(element) {
  return (element && element.businessObject) || element;
}


function is(element, type) {
  var bo = getBusinessObject(element);

  return bo && (typeof bo.$instanceOf === 'function') && bo.$instanceOf(type);
}

exports.getProcessVariables = getProcessVariables;
exports.getVariablesForElement = getVariablesForElement;
exports.getVariablesForScope = getVariablesForScope;
