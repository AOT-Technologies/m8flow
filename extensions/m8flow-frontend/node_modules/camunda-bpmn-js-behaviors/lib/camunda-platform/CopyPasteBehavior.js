import {
  is,
  isAny
} from 'bpmn-js/lib/util/ModelUtil';

import {
  isObject,
  some
} from 'min-dash';

const WILDCARD = '*';


export default class CopyPasteBehavior {
  constructor(eventBus) {
    eventBus.on('moddleCopy.canCopyProperty', (context) => {
      const {
        parent,
        property
      } = context;

      return this.canCopyProperty(property, parent);
    });
  }

  /**
   * Check wether to disallow copying property.
   */
  canCopyProperty(property, parent) {

    // (1) check wether property is allowed in parent
    if (isObject(property) && !isAllowedInParent(property, parent)) {

      return false;
    }

    // (2) check more complex scenarios
    if (is(property, 'camunda:InputOutput') && !this.canHostInputOutput(parent)) {
      return false;
    }

    if (isAny(property, [ 'camunda:Connector', 'camunda:Field' ]) && !this.canHostConnector(parent)) {
      return false;
    }

    if (is(property, 'camunda:In') && !this.canHostIn(parent)) {
      return false;
    }
  }

  canHostInputOutput(parent) {

    // allowed in camunda:Connector
    const connector = getParent(parent, 'camunda:Connector');

    if (connector) {
      return true;
    }

    // special rules inside bpmn:FlowNode
    const flowNode = getParent(parent, 'bpmn:FlowNode');

    if (!flowNode) {
      return false;
    }

    if (isAny(flowNode, [ 'bpmn:StartEvent', 'bpmn:Gateway', 'bpmn:BoundaryEvent' ])) {
      return false;
    }

    if (is(flowNode, 'bpmn:SubProcess') && flowNode.get('triggeredByEvent')) {
      return false;
    }

    return true;
  }

  canHostConnector(parent) {
    const serviceTaskLike = getParent(parent, 'camunda:ServiceTaskLike');

    if (is(serviceTaskLike, 'bpmn:MessageEventDefinition')) {

      // only allow on throw and end events
      return (
        getParent(parent, 'bpmn:IntermediateThrowEvent')
        || getParent(parent, 'bpmn:EndEvent')
      );
    }

    return true;
  }

  canHostIn(parent) {
    const callActivity = getParent(parent, 'bpmn:CallActivity');

    if (callActivity) {
      return true;
    }

    const signalEventDefinition = getParent(parent, 'bpmn:SignalEventDefinition');

    if (signalEventDefinition) {

      // only allow on throw and end events
      return (
        getParent(parent, 'bpmn:IntermediateThrowEvent')
        || getParent(parent, 'bpmn:EndEvent')
      );
    }

    return true;
  }
}

CopyPasteBehavior.$inject = [ 'eventBus' ];


// helpers //////////

function getParent(element, type) {
  if (!type) {
    return element.$parent;
  }

  if (is(element, type)) {
    return element;
  }

  if (!element.$parent) {
    return;
  }

  return getParent(element.$parent, type);
}

function isAllowedInParent(property, parent) {

  // (1) find property descriptor
  var descriptor = property.$type && property.$model.getTypeDescriptor(property.$type);

  var allowedIn = descriptor && descriptor.meta && descriptor.meta.allowedIn;

  if (!allowedIn || isWildcard(allowedIn)) {
    return true;
  }

  // (2) check wether property has parent of allowed type
  return some(allowedIn, function(type) {
    return getParent(parent, type);
  });
}

function isWildcard(allowedIn) {
  return allowedIn.includes(WILDCARD);
}