/**
 * "Node-Wire Connectors" tabs (Action / Config / Parameters) on Service Tasks
 * — ported from `Connector Panel Variations.dc.html`'s "1C · Tabs" mockup.
 *
 * bpmn-js-spiffworkflow's own `ExtensionsPropertiesProvider` already
 * contributes a `service_task_properties` group (operator select + response
 * variable + a flat parameters list, all stacked vertically — no tabs). This
 * provider registers *after* it (see `Modeler.ts`'s `_m8flowModules` order,
 * same trick `externalFormPropertiesProvider.ts` uses) and replaces that
 * group in place with a tabbed version, reusing the vendored field
 * components (`ServiceTaskOperatorSelect`, `ServiceTaskResultTextInput`,
 * `ServiceTaskParameterArray`) for the actual moddle read/write logic rather
 * than re-deriving it — same reasoning as `externalFormPropertiesProvider.ts`.
 *
 * Only the Action and Parameters tabs correspond to real, already-wired
 * functionality (operator/response-variable fields; per-operation
 * parameters from the host catalog). Parameters are rendered as
 * "1A · Stacked cards"' param list (bordered card, mono name above a
 * compact input, separated by a top border) rather than
 * `@bpmn-io/properties-panel`'s `ListGroup` — the library default renders
 * each parameter as a collapsed accordion item (name behind a toggle arrow,
 * value hidden until expanded), which doesn't match any mockup and made
 * every parameter two clicks away from being visible.
 *
 * The vendor `ServiceTaskOperatorSelect` ignores an empty catalog and
 * re-requests forever; the Action tab therefore waits on
 * `serviceTaskOperatorCatalog` (which *does* cache empty) and only mounts
 * that select when HTTP V2 operators actually arrived. An empty catalog is
 * an honest empty state, not a blank dropdown.
 *
 * The Config tab is a connector-profile picker: it writes `m8flow_profile`
 * (quoted profile_name) and the Parameters tab hides profile-supplied
 * basic-auth rows when a profile is set. URL / headers / query / body stay.
 * Empty profile list is allowed — the task can still use `M8FLOW_SECRET:`.
 *
 * No JSX here (unlike the vendored `.jsx` files) — this file isn't matched
 * by `vite/index.js`'s `spiffworkflowPreactJsxPlugin` (scoped to
 * `node_modules/bpmn-js-spiffworkflow/**​/*.jsx`), so JSX here would compile
 * through the *host* app's own React transform instead of Preact's,
 * producing React vnodes the properties panel (a Preact tree) can't render
 * — confirmed as a real, previously-hit failure mode in that file's own
 * alias comments. `preact`'s `h()` hyperscript sidesteps the JSX-transform
 * question entirely: `preact`/`preact/hooks` are aliased to one canonical
 * instance host-wide (not scoped to `.jsx` files), so plain `h()` calls
 * resolve to the same Preact instance the panel itself uses.
 */
import { h } from 'preact';
import { useEffect } from 'preact/hooks';
import { is } from 'bpmn-js/lib/util/ModelUtil';
// @ts-expect-error missing type declarations
import { SelectEntry, TextFieldEntry } from '@bpmn-io/properties-panel';
// @ts-expect-error missing type declarations
import { useService } from 'bpmn-js-properties-panel';
// @ts-expect-error missing type declarations
import { ServiceTaskOperatorSelect, ServiceTaskParameterArray, ServiceTaskResultTextInput } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionServiceProperties';

import { createElementScopedTabStore, useElementScopedTab } from './elementScopedTabState';
import { replaceOrAppendGroup } from './propertiesPanelGroups';
import {
  catalogHasOperators,
  serviceTaskOperatorCatalog,
  useServiceTaskOperatorCatalog,
} from './serviceTaskOperatorCatalog';
import {
  HTTP_PROFILE_FIELD_IDS,
  blankSuppliedParameters,
  connectorTypeForOperator,
  createProfileMemory,
  displayStringParameter,
  hiddenParameterIds,
  quoteStringParameterIfLiteral,
  selectedProfileName,
  visibleParameterItems,
  writeProfileParameter,
} from './connectorProfileBinding';
import {
  CONNECTOR_PROFILES_REQUESTED,
  CONNECTOR_PROFILES_RETURNED,
  connectorProfileCatalog,
  useConnectorProfileCatalog,
} from './connectorProfileCatalog';

const LOW_PRIORITY = 500;
const SERVICE_TASK_GROUP_ID = 'service_task_properties';
// Matches bpmn-js-spiffworkflow's own (unexported) SERVICE_TASK_OPERATOR_ELEMENT_NAME —
// `${SPIFFWORKFLOW_XML_NAMESPACE}:ServiceTaskOperator` with SPIFFWORKFLOW_XML_NAMESPACE === 'spiffworkflow'.
const SERVICE_TASK_OPERATOR_ELEMENT_NAME = 'spiffworkflow:ServiceTaskOperator';

type ServiceTaskTabId = 'action' | 'config' | 'parameters';

// Per-element active-tab store — same pattern bpmn-js-spiffworkflow's own
// SpiffExtensionServiceProperties.js already uses for per-element parameter
// memory (`previouslyUsedServiceTaskParameterValuesHash`). Tab entries are
// separate preact components (see the Group/Entry render loop this
// replaces — no per-entry wrapper, so there's no single parent to hold
// this as local state); `elementScopedTabState.ts` is the shared pub-sub
// that lets the tab strip's click handler notify the sibling content
// entries to re-render.
const serviceTaskTabStore = createElementScopedTabStore<ServiceTaskTabId>('action');
const profileMemory = createProfileMemory();

function setActiveServiceTaskTab(elementId: string, tab: ServiceTaskTabId): void {
  serviceTaskTabStore.setActiveTab(elementId, tab);
}

function useActiveServiceTaskTab(elementId: string): ServiceTaskTabId {
  return useElementScopedTab(serviceTaskTabStore, elementId);
}

function getServiceTaskOperatorModdleElement(element: any): any {
  const { extensionElements } = element.businessObject;
  if (!extensionElements) {
    return null;
  }
  return (
    extensionElements.values.find((ee: any) => ee.$type === SERVICE_TASK_OPERATOR_ELEMENT_NAME) ?? null
  );
}

function getServiceTaskParameterCount(element: any): number {
  const operatorElement = getServiceTaskOperatorModdleElement(element);
  const parameters = operatorElement?.parameterList?.parameters;
  return Array.isArray(parameters) ? parameters.length : 0;
}

// Mirrors connectors_controller.py's _humanize_connector_key fallback (same
// "strip a trailing _v<N>, title-case the rest" rule), applied client-side since
// the operator id ("http/GetRequestV2") is all that's on the moddle element —
// no round trip needed just to render a label.
function humanizeConnectorKey(key: string): string {
  return key
    .replace(/_v\d+$/i, '')
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function ServiceTaskTabStrip(props: any) {
  const { element, translate } = props;
  const elementId = element.businessObject.id;
  const activeTab = useActiveServiceTaskTab(elementId);
  const parameterCount = getServiceTaskParameterCount(element);

  const tabs: { id: ServiceTaskTabId; label: string; badge?: number }[] = [
    { id: 'action', label: translate('Action') },
    { id: 'config', label: translate('Config') },
    { id: 'parameters', label: translate('Parameters'), badge: parameterCount },
  ];

  return h(
    'div',
    { class: 'm8flow-service-task-tabs', role: 'tablist' },
    tabs.map((tab) =>
      h(
        'button',
        {
          type: 'button',
          role: 'tab',
          key: tab.id,
          'aria-selected': activeTab === tab.id,
          class: `m8flow-service-task-tab${activeTab === tab.id ? ' active' : ''}`,
          onClick: () => setActiveServiceTaskTab(elementId, tab.id),
        },
        tab.label,
        tab.badge !== undefined
          ? h('span', { class: 'm8flow-service-task-tab-badge' }, String(tab.badge))
          : null,
      ),
    ),
  );
}

function ServiceTaskActionTab(props: any) {
  const { element, translate } = props;
  const activeTab = useActiveServiceTaskTab(element.businessObject.id);
  const catalog = useServiceTaskOperatorCatalog();
  const eventBus = useService('eventBus');

  // Request once from idle. Do not mount ServiceTaskOperatorSelect until the
  // catalog is known-non-empty: that component ignores an empty returned
  // list and re-fires `.requested` every render, which looks like a blank
  // dropdown and loops `GET /connectors-grouped`.
  useEffect(() => {
    if (serviceTaskOperatorCatalog.markLoading()) {
      eventBus.fire('spiff.service_tasks.requested', { eventBus });
    }
  }, [eventBus]);

  if (activeTab !== 'action') {
    return null;
  }

  if (catalog.status !== 'loaded') {
    return h(
      'p',
      { class: 'bio-properties-panel-description m8flow-service-task-tab-panel' },
      translate('Loading connector actions…'),
    );
  }

  if (!catalogHasOperators(catalog)) {
    return h(
      'p',
      { class: 'bio-properties-panel-description m8flow-service-task-tab-panel' },
      translate(
        'No connector operators are available. HTTP V2 actions appear here when the connector-proxy catalog is reachable.',
      ),
    );
  }

  return h(
    'div',
    { class: 'm8flow-service-task-tab-panel' },
    h(ServiceTaskOperatorSelect, props),
    h(ServiceTaskResultTextInput, props),
  );
}

function ServiceTaskConfigTab(props: any) {
  const { element, translate, commandStack, moddle } = props;
  const activeTab = useActiveServiceTaskTab(element.businessObject.id);
  const eventBus = useService('eventBus');
  const debounce = useService('debounceInput');

  const operatorElement = getServiceTaskOperatorModdleElement(element);
  const connectorType = connectorTypeForOperator(String(operatorElement?.id ?? ''));
  const catalog = useConnectorProfileCatalog(connectorType);

  useEffect(() => {
    if (!connectorType) {
      return;
    }
    if (connectorProfileCatalog.markLoading(connectorType)) {
      eventBus.fire(CONNECTOR_PROFILES_REQUESTED, { eventBus, connectorType });
    }
  }, [eventBus, connectorType]);

  if (activeTab !== 'config') {
    return null;
  }

  if (!operatorElement) {
    return h(
      'p',
      { class: 'bio-properties-panel-description m8flow-service-task-tab-panel' },
      translate('Choose an action first — its connector configuration will show here.'),
    );
  }

  const connectorName = humanizeConnectorKey(connectorType);
  const fieldIds =
    catalog.status === 'loaded' && catalog.entry.hiddenFieldIds.length
      ? catalog.entry.hiddenFieldIds
      : [...HTTP_PROFILE_FIELD_IDS];
  const supportsProfiles = catalog.status !== 'loaded' || catalog.entry.supportsProfiles;

  if (catalog.status === 'loaded' && !catalog.entry.supportsProfiles) {
    return h(
      'div',
      { class: 'm8flow-service-task-tab-panel' },
      h('div', { class: 'm8flow-service-task-config-connector' }, connectorName),
      h(
        'p',
        { class: 'bio-properties-panel-description m8flow-service-task-config-note' },
        translate(
          'This connector has no profiles. Set parameters on this task, or use a secret sentinel.',
        ),
      ),
    );
  }

  if (catalog.status !== 'loaded') {
    return h(
      'div',
      { class: 'm8flow-service-task-tab-panel' },
      h('div', { class: 'm8flow-service-task-config-connector' }, connectorName),
      h(
        'p',
        { class: 'bio-properties-panel-description' },
        translate('Loading connector profiles…'),
      ),
    );
  }

  const profiles = catalog.entry.profiles;
  const getValue = () => selectedProfileName(operatorElement);
  const setValue = (value: string) => {
    writeProfileParameter(operatorElement, moddle, value);
    if (value) {
      blankSuppliedParameters(operatorElement, fieldIds);
      profileMemory.remember(element.id, connectorType, value);
    } else {
      profileMemory.forget(element.id);
    }
    commandStack.execute('element.updateModdleProperties', {
      element,
      moddleElement: element.businessObject,
      properties: {},
    });
  };

  return h(
    'div',
    { class: 'm8flow-service-task-tab-panel' },
    h('div', { class: 'm8flow-service-task-config-connector' }, connectorName),
    h(SelectEntry, {
      id: 'm8flowConnectorProfile',
      element,
      label: translate('Connector profile'),
      description: translate(
        'Credentials come from the selected profile. Manage profiles under Setup → Connectors.',
      ),
      getValue,
      setValue,
      getOptions: () => [
        { label: translate('None — set parameters on this task'), value: '' },
        ...profiles.map((profile) => ({
          label: profile.display_name,
          value: profile.profile_name,
        })),
      ],
      debounce,
    }),
    supportsProfiles && profiles.length === 0
      ? h(
          'p',
          { class: 'bio-properties-panel-description m8flow-service-task-config-note' },
          translate(
            'No profiles yet. Create one under Setup → Connectors, or set parameters on this task.',
          ),
        )
      : null,
  );
}

// One parameter row — name (mono, bold) above its value input, no accordion
// chrome. Mirrors bpmn-js-spiffworkflow's own (unexported)
// ServiceTaskParameterTextField's get/set logic exactly (same
// `element.updateModdleProperties` write, same `.value` read) rather than
// reaching into ServiceTaskParameterArray's returned entries to find that
// component — it isn't part of the module's exports, and duplicating six
// lines of already-proven read/write logic here is simpler than depending
// on an internal shape.
function ServiceTaskParameterRow(props: any) {
  const { element, commandStack, name, serviceTaskParameterModdleElement } = props;
  const debounce = useService('debounceInput');

  const getValue = () => displayStringParameter(serviceTaskParameterModdleElement.value);
  const setValue = (value: string) => {
    commandStack.execute('element.updateModdleProperties', {
      element,
      moddleElement: serviceTaskParameterModdleElement,
      properties: { value: quoteStringParameterIfLiteral(value) },
    });
  };

  return h(
    'div',
    { class: 'm8flow-service-task-param-row' },
    h('div', { class: 'm8flow-service-task-param-name' }, name),
    h(TextFieldEntry, {
      element,
      id: `serviceTaskParameter-${name}-textField`,
      getValue,
      setValue,
      debounce,
    }),
  );
}

// "1A · Stacked cards" reference (Connector Panel Variations.dc.html) for the
// visual structure — a single bordered card, sunken header, param rows
// separated by a top border, name in mono type above a compact input. The
// mockup's card repeats a "Parameters" title + count inside the card, which
// this tab omits: the tab strip above already shows both.
function ServiceTaskParametersTab(props: any) {
  const { element, moddle, translate, commandStack } = props;
  const activeTab = useActiveServiceTaskTab(element.businessObject.id);
  if (activeTab !== 'parameters') {
    return null;
  }

  if (!getServiceTaskOperatorModdleElement(element)) {
    return h(
      'p',
      { class: 'bio-properties-panel-description m8flow-service-task-tab-panel' },
      translate('Choose an action first — its parameters will show here.'),
    );
  }

  // Pure data transform, no hooks of its own — safe to call directly. Reused
  // only for its moddle traversal (getServiceTaskParameterModdleElements,
  // unexported); the rows below render their own markup, not this array's
  // ListGroup-shaped `entries`.
  const { items } = ServiceTaskParameterArray({ element, moddle, translate, commandStack });
  const operatorElement = getServiceTaskOperatorModdleElement(element);
  const connectorType = connectorTypeForOperator(String(operatorElement?.id ?? ''));
  const catalog = connectorProfileCatalog.getState(connectorType);
  const fieldIds =
    catalog.status === 'loaded' && catalog.entry.hiddenFieldIds.length
      ? catalog.entry.hiddenFieldIds
      : [...HTTP_PROFILE_FIELD_IDS];
  const hidden = hiddenParameterIds(Boolean(selectedProfileName(operatorElement)), fieldIds);
  const visibleItems = visibleParameterItems(items, hidden);

  if (visibleItems.length === 0) {
    return h(
      'p',
      { class: 'bio-properties-panel-description m8flow-service-task-tab-panel' },
      translate('This action has no parameters.'),
    );
  }

  return h(
    'div',
    { class: 'm8flow-service-task-tab-panel m8flow-service-task-params-card' },
    visibleItems.map((item: any) =>
      h(ServiceTaskParameterRow, {
        key: item.id,
        element,
        commandStack,
        name: item.label,
        serviceTaskParameterModdleElement: item.entries[0].serviceTaskParameterModdleElement,
      }),
    ),
  );
}

function createServiceTaskConnectorGroup(element: any, translate: any, moddle: any, commandStack: any) {
  const sharedProps = { element, moddle, commandStack, translate };
  return {
    id: SERVICE_TASK_GROUP_ID,
    label: translate('Node-Wire Connectors'),
    entries: [
      { id: 'service_task_tabs', component: ServiceTaskTabStrip, ...sharedProps },
      { id: 'service_task_action_tab', component: ServiceTaskActionTab, ...sharedProps },
      { id: 'service_task_config_tab', component: ServiceTaskConfigTab, ...sharedProps },
      { id: 'service_task_parameters_tab', component: ServiceTaskParametersTab, ...sharedProps },
    ],
  };
}

export function ServiceTaskConnectorPanelProvider(
  this: any,
  propertiesPanel: any,
  translate: any,
  moddle: any,
  commandStack: any,
  eventBus: any,
) {
  eventBus.on('spiff.service_tasks.returned', (event: { serviceTaskOperators?: unknown }) => {
    const operators = Array.isArray(event?.serviceTaskOperators) ? event.serviceTaskOperators : [];
    serviceTaskOperatorCatalog.setLoaded(operators);
  });
  eventBus.on(
    CONNECTOR_PROFILES_RETURNED,
    (event: { connectorType?: string; profiles?: unknown; hiddenFieldIds?: unknown; supportsProfiles?: unknown }) => {
      if (typeof event?.connectorType === 'string' && event.connectorType) {
        connectorProfileCatalog.setLoaded(event.connectorType, event);
      }
    },
  );
  eventBus.on('diagram.destroy', () => {
    connectorProfileCatalog.reset();
    profileMemory.reset();
  });
  this.getGroups = function (element: any) {
    return function (groups: any[]) {
      if (!is(element, 'bpmn:ServiceTask')) {
        return groups;
      }
      const operator = getServiceTaskOperatorModdleElement(element);
      if (operator) {
        const connectorType = connectorTypeForOperator(String(operator.id ?? ''));
        const catalog = connectorProfileCatalog.getState(connectorType);
        const fieldIds =
          catalog.status === 'loaded' && catalog.entry.hiddenFieldIds.length
            ? catalog.entry.hiddenFieldIds
            : [...HTTP_PROFILE_FIELD_IDS];
        profileMemory.reconcile(element.id, operator, connectorType, moddle, fieldIds);
      }
      const tabbedGroup = createServiceTaskConnectorGroup(element, translate, moddle, commandStack);
      // Replace in place (see propertiesPanelGroups.ts) so the group keeps
      // its original position — between "Instructions" and "Input/Output
      // Management", matching bpmn-js-spiffworkflow's own createServiceGroup
      // ordering — rather than moving to the end of the list.
      return replaceOrAppendGroup(groups, tabbedGroup);
    };
  };
  propertiesPanel.registerProvider(LOW_PRIORITY, this);
}

(ServiceTaskConnectorPanelProvider as any).$inject = [
  'propertiesPanel',
  'translate',
  'moddle',
  'commandStack',
  'eventBus',
];

export const serviceTaskConnectorPanelModule = {
  __init__: ['serviceTaskConnectorPanelProvider'],
  serviceTaskConnectorPanelProvider: ['type', ServiceTaskConnectorPanelProvider],
};
