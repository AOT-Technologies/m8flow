import { SelectEntry } from '@bpmn-io/properties-panel';
import { useService } from 'bpmn-js-properties-panel';
import { is } from 'bpmn-js/lib/util/ModelUtil';
import { SPIFFWORKFLOW_XML_NAMESPACE } from 'bpmn-js-spiffworkflow/app/spiffworkflow/constants';
import { ServiceTaskOperatorSelect } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionServiceProperties';
import {
  connectorTypeForOperator,
  loadConnectorProfiles,
  onConnectorProfilesLoaded,
  profileFieldNames,
  profilesFor,
  supportsProfiles,
} from './connectorProfileStore';

const LOW_PRIORITY = 500;

// The upstream group this provider rewrites, and the entries it works around.
const SERVICE_GROUP_ID = 'service_task_properties';
const OPERATOR_ENTRY_ID = 'selectOperatorId';
const PARAMETERS_ENTRY_ID = 'serviceTaskParameters';

const OPERATOR_TYPE = `${SPIFFWORKFLOW_XML_NAMESPACE}:ServiceTaskOperator`;
const PARAMETERS_TYPE = `${SPIFFWORKFLOW_XML_NAMESPACE}:Parameters`;
const PARAMETER_TYPE = `${SPIFFWORKFLOW_XML_NAMESPACE}:Parameter`;

/**
 * The service-task parameter that binds a task to a connector profile. The
 * backend pops it before calling the connector proxy.
 */
export const PROFILE_PARAMETER_ID = 'm8flow_profile';
export const PROFILE_ENTRY_ID = 'm8flowConnectorProfile';

function operatorElement(element) {
  const values = element?.businessObject?.extensionElements?.values || [];
  return values.find((value) => value.$type === OPERATOR_TYPE) || null;
}

function parameterElements(operator) {
  return operator?.parameterList?.parameters || [];
}

function parameterById(operator, id) {
  return (
    parameterElements(operator).find((parameter) => parameter.id === id) || null
  );
}

/**
 * Parameter values are python expressions, so a literal name has to be quoted.
 */
function quote(name) {
  return JSON.stringify(name);
}

function unquote(rawValue) {
  if (typeof rawValue !== 'string') {
    return '';
  }
  try {
    const parsed = JSON.parse(rawValue.trim());
    return typeof parsed === 'string' ? parsed : '';
  } catch {
    // A hand-edited or templated value we cannot read as a plain name. Treat it
    // as "no profile" rather than throwing: the author keeps whatever they wrote.
    return '';
  }
}

/**
 * Remember which connector each element's profile was chosen for.
 *
 * Upstream's operator dropdown rebuilds parameterList from scratch on change,
 * containing only the new operator's declared parameters -- so a sibling
 * m8flow_profile parameter is silently dropped. We re-add it when the new
 * operator belongs to the same connector, and let it stay gone when it does not,
 * because a profile means nothing across connectors.
 */
const lastConnectorByElement = new Map();
const lastProfileByElement = new Map();

export function resetProfileMemory() {
  lastConnectorByElement.clear();
  lastProfileByElement.clear();
}

function ensureParameterList(operator, moddle) {
  if (!operator.parameterList) {
    const parameterList = moddle.create(PARAMETERS_TYPE);
    parameterList.parameters = [];
    operator.parameterList = parameterList;
  }
  return operator.parameterList.parameters;
}

function writeProfileParameter(operator, moddle, value) {
  const parameters = ensureParameterList(operator, moddle);
  const existing = parameterById(operator, PROFILE_PARAMETER_ID);

  if (!value) {
    if (existing) {
      parameters.splice(parameters.indexOf(existing), 1);
    }
    return;
  }

  if (existing) {
    existing.value = quote(value);
  } else {
    const parameter = moddle.create(PARAMETER_TYPE);
    parameter.id = PROFILE_PARAMETER_ID;
    parameter.type = 'any';
    parameter.value = quote(value);
    parameters.push(parameter);
  }
}

/**
 * Blank the parameters the profile now supplies, so no credential is left in the
 * diagram. The parameter elements themselves stay: the operation declared them,
 * and clearing the profile brings them back.
 */
function blankSuppliedParameters(operator, connectorType) {
  const supplied = profileFieldNames(connectorType);
  parameterElements(operator).forEach((parameter) => {
    if (supplied.includes(parameter.id)) {
      parameter.value = undefined;
    }
  });
}

export function ConnectorProfileSelect(props) {
  const { element, commandStack, moddle, translate } = props;
  const debounce = useService('debounceInput');

  const operator = operatorElement(element);
  const connectorType = connectorTypeForOperator(operator ? operator.id : '');

  const getValue = () =>
    unquote(parameterById(operator, PROFILE_PARAMETER_ID)?.value);

  const setValue = (value) => {
    if (!operator) {
      return;
    }
    writeProfileParameter(operator, moddle, value);
    if (value) {
      blankSuppliedParameters(operator, connectorType);
      lastConnectorByElement.set(element.id, connectorType);
      lastProfileByElement.set(element.id, value);
    } else {
      lastConnectorByElement.delete(element.id);
      lastProfileByElement.delete(element.id);
    }

    commandStack.execute('element.updateModdleProperties', {
      element,
      moddleElement: element.businessObject,
      properties: {},
    });
  };

  const getOptions = () => [
    { label: translate('None - set parameters manually'), value: '' },
    ...profilesFor(connectorType).map((profile) => ({
      label: profile.is_default
        ? `${profile.display_name} (${translate('default')})`
        : profile.display_name,
      value: profile.profile_name,
    })),
  ];

  return SelectEntry({
    id: PROFILE_ENTRY_ID,
    element,
    label: translate('Connector profile'),
    description: translate(
      'Credentials come from the selected profile. Manage profiles under Connectors.',
    ),
    getValue,
    setValue,
    getOptions,
    debounce,
  });
}

/**
 * Adds the "Connector profile" dropdown to the service task group and hides the
 * parameters the selected profile supplies.
 *
 * Registered after bpmn-js-spiffworkflow so the group it rewrites already
 * exists. Nothing in node_modules is patched.
 */
export default function ConnectorProfilePropertiesProvider(
  propertiesPanel,
  translate,
  moddle,
  commandStack,
  eventBus,
  selection,
) {
  // The panel renders synchronously, so a service task's first render can only
  // start the load. Re-render the current selection once it lands.
  onConnectorProfilesLoaded(() => {
    const selected = selection && selection.get ? selection.get() : [];
    if (selected.length) {
      eventBus.fire('elements.changed', { elements: selected });
    }
  });

  /**
   * Restore a profile parameter that an operator change discarded.
   *
   * Returns the profile name now in effect, which is '' when the author moved to
   * a different connector and the profile was therefore dropped for good.
   */
  function reconcileAfterOperatorChange(element, operator, connectorType) {
    const current = unquote(parameterById(operator, PROFILE_PARAMETER_ID)?.value);
    if (current) {
      lastConnectorByElement.set(element.id, connectorType);
      lastProfileByElement.set(element.id, current);
      return current;
    }

    const remembered = lastConnectorByElement.get(element.id);
    if (!remembered) {
      return '';
    }
    if (remembered !== connectorType) {
      // A different connector: the old profile cannot apply here.
      lastConnectorByElement.delete(element.id);
      lastProfileByElement.delete(element.id);
      return '';
    }
    // Same connector, profile parameter gone -- upstream rebuilt the list. The
    // author's choice still holds, so put it back.
    const selected = lastProfileByElement.get(element.id);
    if (!selected) {
      return '';
    }
    writeProfileParameter(operator, moddle, selected);
    blankSuppliedParameters(operator, connectorType);
    return selected;
  }

  this.getGroups = function getGroups(element) {
    return function rewrite(groups) {
      if (!is(element, 'bpmn:ServiceTask')) {
        return groups;
      }

      const group = groups.find(
        (candidate) => candidate && candidate.id === SERVICE_GROUP_ID,
      );
      if (!group || !Array.isArray(group.entries)) {
        return groups;
      }

      const operator = operatorElement(element);
      const connectorType = connectorTypeForOperator(
        operator ? operator.id : '',
      );
      if (!connectorType || !supportsProfiles(connectorType)) {
        // No operator chosen yet, or a connector with nothing to configure.
        // Kick off the load so the dropdown can appear once an operator is set.
        loadConnectorProfiles();
        return groups;
      }

      const alreadyAdded = group.entries.some(
        (entry) => entry && entry.id === PROFILE_ENTRY_ID,
      );
      if (!alreadyAdded) {
        // Upstream builds the operator entry with a component and no id -- the
        // id lives on the SelectEntry that component returns -- so match on the
        // component first and fall back to the position it is built in.
        const operatorIndex = group.entries.findIndex(
          (entry) =>
            entry &&
            (entry.component === ServiceTaskOperatorSelect ||
              entry.id === OPERATOR_ENTRY_ID),
        );
        const insertAt =
          operatorIndex === -1
            ? Math.min(1, group.entries.length)
            : operatorIndex + 1;
        group.entries.splice(insertAt, 0, {
          id: PROFILE_ENTRY_ID,
          element,
          moddle,
          commandStack,
          translate,
          component: ConnectorProfileSelect,
        });
      }

      const selectedProfile = reconcileAfterOperatorChange(
        element,
        operator,
        connectorType,
      );

      const hidden = new Set([PROFILE_PARAMETER_ID]);
      if (selectedProfile) {
        profileFieldNames(connectorType).forEach((name) => hidden.add(name));
      }

      const parameters = group.entries.find(
        (entry) => entry && entry.id === PARAMETERS_ENTRY_ID,
      );
      if (parameters && Array.isArray(parameters.items)) {
        // Upstream labels each parameter row with the parameter's id.
        parameters.items = parameters.items.filter(
          (item) => !hidden.has(item.label),
        );
        if (parameters.items.length === 0) {
          group.entries = group.entries.filter((entry) => entry !== parameters);
        }
      }

      return groups;
    };
  };

  propertiesPanel.registerProvider(LOW_PRIORITY, this);
}

ConnectorProfilePropertiesProvider.$inject = [
  'propertiesPanel',
  'translate',
  'moddle',
  'commandStack',
  'eventBus',
  'selection',
];
