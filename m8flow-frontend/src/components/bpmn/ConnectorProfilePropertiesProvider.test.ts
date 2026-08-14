import { describe, it, expect, vi, beforeEach } from 'vitest';

// The properties-panel render stack is not under test here.
vi.mock('@bpmn-io/properties-panel', () => ({
  SelectEntry: (props: any) => props,
}));
vi.mock('bpmn-js-properties-panel', () => ({
  useService: () => undefined,
}));

import { ServiceTaskOperatorSelect } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionServiceProperties';
import ConnectorProfilePropertiesProvider, {
  ConnectorProfileSelect,
  PROFILE_ENTRY_ID,
  PROFILE_PARAMETER_ID,
} from './ConnectorProfilePropertiesProvider';
import {
  primeConnectorProfiles,
  resetConnectorProfiles,
} from './connectorProfileStore';

const SMTP_TEMPLATE = {
  id: 'smtp',
  name: 'SMTP',
  description: '',
  category: 'messaging',
  icon: 'email',
  docsUrl: '',
  supportsProfiles: true,
  testOperation: null,
  groups: [],
  profileFields: [
    { id: 'smtp_host', label: 'Host', type: 'text', required: true, group: 'connection', binding: 'config_param', secret: false },
    { id: 'smtp_password', label: 'Password', type: 'password', required: false, group: 'authentication', binding: 'secret_param', secret: true },
  ],
  taskFields: [],
};

const HTTP_TEMPLATE = { ...SMTP_TEMPLATE, id: 'http', name: 'HTTP', supportsProfiles: false, profileFields: [] };

const STAGING = {
  id: 1,
  connector_type: 'smtp',
  profile_name: 'smtp-staging',
  display_name: 'SMTP Staging',
  description: null,
  config: {},
  configured_secrets: ['smtp_password'],
  is_active: true,
  is_default: false,
};
const PRODUCTION = { ...STAGING, id: 2, profile_name: 'smtp-production', display_name: 'SMTP Production', is_default: true };
const SLACK_PROFILE = { ...STAGING, id: 3, connector_type: 'slack', profile_name: 'slack-prod', display_name: 'Slack' };

/** A service task carrying an operator and its parameter list. */
function makeServiceTask(operatorId: string, parameters: any[]) {
  const businessObject: any = {
    $instanceOf: (candidate: string) => candidate === 'bpmn:ServiceTask',
    extensionElements: {
      values: [
        {
          $type: 'spiffworkflow:ServiceTaskOperator',
          id: operatorId,
          parameterList: { parameters },
        },
      ],
    },
  };
  return { businessObject };
}

/**
 * The service task group as bpmn-js-spiffworkflow builds it: the operator and
 * result entries carry a `component` and no `id` (their ids live on the entries
 * their components return), and only the parameter list has an id.
 */
function makeGroups(parameterIds: string[]) {
  return [
    { id: 'general', entries: [] },
    {
      id: 'service_task_properties',
      entries: [
        { component: ServiceTaskOperatorSelect },
        { component: function ServiceTaskResultTextInput() {} },
        {
          id: 'serviceTaskParameters',
          items: parameterIds.map((id, index) => ({ id: `serviceTaskParameter-${index}`, label: id })),
        },
      ],
    },
  ];
}

function instantiate() {
  const registered: any[] = [];
  const created: any[] = [];
  const executed: any[] = [];
  const propertiesPanel = {
    registerProvider: (priority: number, provider: any) => registered.push({ priority, provider }),
  };
  const moddle = {
    create: (type: string) => {
      const element = { $type: type };
      created.push(element);
      return element;
    },
  };
  const commandStack = { execute: (...args: any[]) => executed.push(args) };
  const eventBus = { fire: vi.fn() };
  const selection = { get: () => [] };
  const provider: any = new (ConnectorProfilePropertiesProvider as any)(
    propertiesPanel,
    (text: string) => text,
    moddle,
    commandStack,
    eventBus,
    selection,
  );
  return { provider, registered, moddle, commandStack, executed };
}

describe('ConnectorProfilePropertiesProvider', () => {
  beforeEach(() => {
    resetConnectorProfiles();
    primeConnectorProfiles(
      [SMTP_TEMPLATE, HTTP_TEMPLATE] as any,
      [STAGING, PRODUCTION, SLACK_PROFILE] as any,
    );
  });

  it('registers itself as a properties-panel provider', () => {
    const { registered } = instantiate();
    expect(registered).toHaveLength(1);
    expect(typeof registered[0].provider.getGroups).toBe('function');
  });

  it('adds the profile select directly below the operator select', () => {
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', []);

    const groups = provider.getGroups(element)(makeGroups(['smtp_host', 'email_to']));

    const service = groups.find((group: any) => group.id === 'service_task_properties');
    expect(service.entries[0].component).toBe(ServiceTaskOperatorSelect);
    expect(service.entries[1].id).toBe(PROFILE_ENTRY_ID);
  });

  it('leaves non-service-task elements alone', () => {
    const { provider } = instantiate();
    const element = { businessObject: { $instanceOf: (c: string) => c === 'bpmn:UserTask' } };
    const incoming = makeGroups([]);
    expect(provider.getGroups(element)(incoming)).toBe(incoming);
  });

  it('offers no profile select for a connector that has no profile fields', () => {
    const { provider } = instantiate();
    const element = makeServiceTask('http/GetRequestV2', []);

    const groups = provider.getGroups(element)(makeGroups(['url']));

    const service = groups.find((group: any) => group.id === 'service_task_properties');
    expect(service.entries.some((entry: any) => entry.id === PROFILE_ENTRY_ID)).toBe(false);
  });

  it('hides the parameters the selected profile supplies', () => {
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      { id: 'smtp_host' },
      { id: 'smtp_password' },
      { id: 'email_to' },
    ]);

    const groups = provider.getGroups(element)(
      makeGroups([PROFILE_PARAMETER_ID, 'smtp_host', 'smtp_password', 'email_to']),
    );

    const service = groups.find((group: any) => group.id === 'service_task_properties');
    const parameters = service.entries.find((entry: any) => entry.id === 'serviceTaskParameters');
    expect(parameters.items.map((item: any) => item.label)).toEqual(['email_to']);
  });

  it('shows every parameter except the marker when no profile is selected', () => {
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [{ id: 'smtp_host' }, { id: 'email_to' }]);

    const groups = provider.getGroups(element)(makeGroups(['smtp_host', 'email_to']));

    const service = groups.find((group: any) => group.id === 'service_task_properties');
    const parameters = service.entries.find((entry: any) => entry.id === 'serviceTaskParameters');
    expect(parameters.items.map((item: any) => item.label)).toEqual(['smtp_host', 'email_to']);
  });
});

describe('ConnectorProfileSelect', () => {
  beforeEach(() => {
    resetConnectorProfiles();
    primeConnectorProfiles(
      [SMTP_TEMPLATE, HTTP_TEMPLATE] as any,
      [STAGING, PRODUCTION, SLACK_PROFILE] as any,
    );
  });

  function renderSelect(element: any) {
    const created: any[] = [];
    const executed: any[] = [];
    const props = {
      element,
      moddle: {
        create: (type: string) => {
          const created_element: any = { $type: type };
          created.push(created_element);
          return created_element;
        },
      },
      commandStack: { execute: (...args: any[]) => executed.push(args) },
      translate: (text: string) => text,
    };
    return { entry: ConnectorProfileSelect(props as any) as any, executed };
  }

  it('offers only that connector profiles, plus an empty option', () => {
    const { entry } = renderSelect(makeServiceTask('smtp/SendHTMLEmail', []));

    expect(entry.getOptions().map((option: any) => option.value)).toEqual([
      '',
      'smtp-production',
      'smtp-staging',
    ]);
    // The Slack profile must not leak into the SMTP list.
    expect(entry.getOptions().some((option: any) => option.value === 'slack-prod')).toBe(false);
  });

  it('marks the default profile', () => {
    const { entry } = renderSelect(makeServiceTask('smtp/SendHTMLEmail', []));
    const production = entry
      .getOptions()
      .find((option: any) => option.value === 'smtp-production');
    expect(production.label).toContain('default');
  });

  it('reads the profile name out of the quoted parameter value', () => {
    const { entry } = renderSelect(
      makeServiceTask('smtp/SendHTMLEmail', [
        { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      ]),
    );
    expect(entry.getValue()).toBe('smtp-staging');
  });

  it('writes a quoted parameter and blanks what the profile supplies', () => {
    const parameters = [
      { id: 'smtp_host', value: '"M8FLOW_SECRET:SMTP_HOST"' },
      { id: 'smtp_password', value: '"M8FLOW_SECRET:SMTP_PASSWORD"' },
      { id: 'email_to', value: 'f"{email}"' },
    ];
    const element = makeServiceTask('smtp/SendHTMLEmail', parameters);
    const { entry, executed } = renderSelect(element);

    entry.setValue('smtp-staging');

    const marker = parameters.find((parameter: any) => parameter.id === PROFILE_PARAMETER_ID);
    expect(marker).toBeTruthy();
    expect((marker as any).value).toBe('"smtp-staging"');
    // Credentials are gone from the diagram; the task parameter is untouched.
    expect(parameters.find((p: any) => p.id === 'smtp_host')!.value).toBeUndefined();
    expect(parameters.find((p: any) => p.id === 'smtp_password')!.value).toBeUndefined();
    expect(parameters.find((p: any) => p.id === 'email_to')!.value).toBe('f"{email}"');
    expect(executed).toHaveLength(1);
  });

  it('removes the marker when the selection is cleared', () => {
    const parameters = [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      { id: 'smtp_host', value: undefined },
    ];
    const element = makeServiceTask('smtp/SendHTMLEmail', parameters);
    const { entry } = renderSelect(element);

    entry.setValue('');

    expect(parameters.some((p: any) => p.id === PROFILE_PARAMETER_ID)).toBe(false);
    // The parameter rows come back so the author can fill them in by hand.
    expect(parameters.map((p: any) => p.id)).toEqual(['smtp_host']);
  });
});
