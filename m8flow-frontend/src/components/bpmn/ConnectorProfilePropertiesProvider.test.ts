import { describe, it, expect, vi, beforeEach } from 'vitest';

// Stub the bpmn-js render stack: these tests exercise group rewriting and moddle
// writes, not React rendering.
vi.mock('@bpmn-io/properties-panel', () => ({
  SelectEntry: (props: any) => ({ __selectEntry: props }),
}));
vi.mock('bpmn-js-properties-panel', () => ({
  useService: () => (fn: any) => fn,
}));
vi.mock('bpmn-js/lib/util/ModelUtil', () => ({
  is: (element: any, type: string) => element?.businessObject?.$instanceOf(type),
}));
vi.mock('bpmn-js-spiffworkflow/app/spiffworkflow/constants', () => ({
  SPIFFWORKFLOW_XML_NAMESPACE: 'spiffworkflow',
}));
vi.mock(
  'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionServiceProperties',
  () => ({ ServiceTaskOperatorSelect: function OperatorSelectStub() {} }),
);
// The store reaches for HttpService on load; these tests prime it directly.
vi.mock('../../services/HttpService', () => ({
  default: { makeCallToBackend: () => {} },
}));

import ConnectorProfilePropertiesProvider, {
  ConnectorProfileSelect,
  PROFILE_ENTRY_ID,
  PROFILE_PARAMETER_ID,
  resetProfileMemory,
} from './ConnectorProfilePropertiesProvider';
import {
  primeConnectorProfiles,
  resetConnectorProfiles,
  type ConnectorProfile,
  type ConnectorTemplate,
} from './connectorProfileStore';

const OPERATOR_TYPE = 'spiffworkflow:ServiceTaskOperator';

const smtpTemplate = (): ConnectorTemplate => ({
  id: 'smtp',
  definitionId: 'm8flow.smtp.v1',
  name: 'SMTP',
  description: '',
  category: 'messaging',
  icon: 'email',
  docsUrl: '',
  supportsProfiles: true,
  groups: [],
  profileFields: [
    {
      id: 'smtp_host',
      label: 'Host',
      type: 'text',
      required: true,
      group: 'connection',
      binding: 'config_param',
      secret: false,
    },
    {
      id: 'smtp_password',
      label: 'Password',
      type: 'password',
      required: true,
      group: 'authentication',
      binding: 'secret_param',
      secret: true,
    },
  ],
  taskFields: [
    {
      id: 'email_to',
      label: 'To',
      type: 'text',
      required: true,
      group: 'task',
      binding: 'task_param',
      secret: false,
    },
  ],
});

const slackTemplate = (): ConnectorTemplate => ({
  ...smtpTemplate(),
  id: 'slack',
  name: 'Slack',
  profileFields: [
    {
      id: 'token',
      label: 'Token',
      type: 'password',
      required: true,
      group: 'authentication',
      binding: 'secret_param',
      secret: true,
    },
  ],
});

const profile = (over: Partial<ConnectorProfile>): ConnectorProfile => ({
  id: '01234567-89ab-cdef-0123-456789abcdef',
  connector_type: 'smtp',
  profile_name: 'smtp-staging',
  display_name: 'SMTP Staging',
  description: null,
  config: {},
  configured_secrets: [],
  is_active: true,
  ...over,
});

/** A service task element carrying an operator and its parameters. */
function makeServiceTask(
  operatorId: string,
  parameters: { id: string; value?: string }[] = [],
  elementId = 'Task_1',
) {
  const operator: any = {
    $type: OPERATOR_TYPE,
    id: operatorId,
    parameterList: { parameters: parameters.map((p) => ({ type: 'any', ...p })) },
  };
  return {
    id: elementId,
    businessObject: {
      id: elementId,
      $instanceOf: (candidate: string) => candidate === 'bpmn:ServiceTask',
      extensionElements: { values: [operator] },
    },
    __operator: operator,
  } as any;
}

function makeGroups(element: any, parameterItems?: string[]) {
  const entries: any[] = [
    { element, component: function OperatorSelectStub() {} },
    { element, component: function ResultVariableStub() {} },
  ];
  if (parameterItems) {
    entries.push({
      id: 'serviceTaskParameters',
      label: 'Parameters',
      items: parameterItems.map((label, index) => ({
        id: `serviceTaskParameter-${index}`,
        label,
      })),
    });
  }
  return [{ id: 'service_task_properties', label: 'M8flow Connectors', entries }];
}

const moddle = {
  create: (type: string) =>
    type === 'spiffworkflow:Parameters'
      ? ({ $type: type, parameters: [] } as any)
      : ({ $type: type } as any),
};

function instantiate() {
  const registered: any[] = [];
  const fired: any[] = [];
  const executed: any[] = [];
  const provider: any = new (ConnectorProfilePropertiesProvider as any)(
    { registerProvider: (priority: number, p: any) => registered.push({ priority, p }) },
    (s: string) => s,
    moddle,
    { execute: (...args: any[]) => executed.push(args) },
    { fire: (...args: any[]) => fired.push(args) },
    { get: () => [] },
  );
  return { provider, registered, fired, executed };
}

/** Run the provider's group rewrite and hand back the mutated groups. */
function rewrite(provider: any, element: any, groups: any[]) {
  return provider.getGroups(element)(groups);
}

beforeEach(() => {
  resetConnectorProfiles();
  resetProfileMemory();
});

describe('ConnectorProfilePropertiesProvider', () => {
  it('registers itself as a properties-panel provider', () => {
    const { registered } = instantiate();
    expect(registered).toHaveLength(1);
    expect(registered[0].priority).toBe(500);
    expect(typeof registered[0].p.getGroups).toBe('function');
  });

  it('leaves non-service-task elements alone', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const userTask = {
      businessObject: { $instanceOf: (c: string) => c === 'bpmn:UserTask' },
    };
    const groups = [{ id: 'user_task_properties', entries: [] }];

    expect(rewrite(provider, userTask, groups)).toBe(groups);
    expect(groups[0].entries).toHaveLength(0);
  });

  it('inserts the profile dropdown directly after the operator entry', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail');
    const groups = makeGroups(element);

    rewrite(provider, element, groups);

    const ids = groups[0].entries.map((entry: any) => entry.id);
    expect(ids).toEqual([undefined, PROFILE_ENTRY_ID, undefined]);
  });

  it('does not add the dropdown twice across repeated renders', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail');
    const groups = makeGroups(element);

    rewrite(provider, element, groups);
    rewrite(provider, element, groups);

    const matches = groups[0].entries.filter(
      (entry: any) => entry.id === PROFILE_ENTRY_ID,
    );
    expect(matches).toHaveLength(1);
  });

  it('adds nothing until an operator has been chosen', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('');
    const groups = makeGroups(element);

    rewrite(provider, element, groups);

    expect(
      groups[0].entries.some((entry: any) => entry.id === PROFILE_ENTRY_ID),
    ).toBe(false);
  });

  it('adds nothing for a connector with no profile fields', () => {
    primeConnectorProfiles(
      [{ ...smtpTemplate(), supportsProfiles: false, profileFields: [] }],
      [],
    );
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail');
    const groups = makeGroups(element);

    rewrite(provider, element, groups);

    expect(
      groups[0].entries.some((entry: any) => entry.id === PROFILE_ENTRY_ID),
    ).toBe(false);
  });

  it('hides the profile parameter row so it is never hand-edited', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      { id: 'email_to' },
    ]);
    const groups = makeGroups(element, [PROFILE_PARAMETER_ID, 'email_to']);

    rewrite(provider, element, groups);

    const parameters = groups[0].entries.find(
      (entry: any) => entry.id === 'serviceTaskParameters',
    );
    expect(parameters.items.map((item: any) => item.label)).toEqual(['email_to']);
  });

  it('hides the parameters a selected profile supplies', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      { id: 'smtp_host' },
      { id: 'smtp_password' },
      { id: 'email_to' },
    ]);
    const groups = makeGroups(element, [
      PROFILE_PARAMETER_ID,
      'smtp_host',
      'smtp_password',
      'email_to',
    ]);

    rewrite(provider, element, groups);

    const parameters = groups[0].entries.find(
      (entry: any) => entry.id === 'serviceTaskParameters',
    );
    expect(parameters.items.map((item: any) => item.label)).toEqual(['email_to']);
  });

  it('keeps every parameter visible when no profile is selected', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: 'smtp_host' },
      { id: 'email_to' },
    ]);
    const groups = makeGroups(element, ['smtp_host', 'email_to']);

    rewrite(provider, element, groups);

    const parameters = groups[0].entries.find(
      (entry: any) => entry.id === 'serviceTaskParameters',
    );
    expect(parameters.items.map((item: any) => item.label)).toEqual([
      'smtp_host',
      'email_to',
    ]);
  });

  it('drops the parameters group when the profile supplies everything', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
      { id: 'smtp_host' },
    ]);
    const groups = makeGroups(element, [PROFILE_PARAMETER_ID, 'smtp_host']);

    rewrite(provider, element, groups);

    expect(
      groups[0].entries.some((entry: any) => entry.id === 'serviceTaskParameters'),
    ).toBe(false);
  });
});

describe('ConnectorProfileSelect options', () => {
  function optionsFor(element: any) {
    const entry: any = ConnectorProfileSelect({
      element,
      commandStack: { execute: () => {} },
      moddle,
      translate: (s: string) => s,
    });
    return entry.__selectEntry.getOptions();
  }

  it('lists every active profile saved for that connector', () => {
    primeConnectorProfiles(
      [smtpTemplate()],
      [
        profile({ id: '1', profile_name: 'smtp-staging', display_name: 'Staging' }),
        profile({ id: '2', profile_name: 'smtp-production', display_name: 'Production' }),
        profile({ id: '3', profile_name: 'smtp-dev', display_name: 'Dev' }),
      ],
    );

    const options = optionsFor(makeServiceTask('smtp/SendHTMLEmail'));

    // The empty choice lets authors remove a previously selected profile.
    expect(options.map((o: any) => o.value)).toEqual([
      '',
      'smtp-dev',
      'smtp-production',
      'smtp-staging',
    ]);
  });

  it('grows as more profiles are saved', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({ id: '1' })]);
    expect(optionsFor(makeServiceTask('smtp/SendHTMLEmail'))).toHaveLength(2);

    primeConnectorProfiles(
      [smtpTemplate()],
      [
        profile({ id: '1', profile_name: 'a' }),
        profile({ id: '2', profile_name: 'b' }),
        profile({ id: '3', profile_name: 'c' }),
        profile({ id: '4', profile_name: 'd' }),
      ],
    );
    expect(optionsFor(makeServiceTask('smtp/SendHTMLEmail'))).toHaveLength(5);
  });

  it('scopes the list to the operator’s own connector', () => {
    primeConnectorProfiles(
      [smtpTemplate(), slackTemplate()],
      [
        profile({ id: '1', connector_type: 'smtp', profile_name: 'smtp-prod' }),
        profile({ id: '2', connector_type: 'slack', profile_name: 'slack-team' }),
      ],
    );

    const smtpOptions = optionsFor(makeServiceTask('smtp/SendHTMLEmail'));
    expect(smtpOptions.map((o: any) => o.value)).toEqual(['', 'smtp-prod']);

    const slackOptions = optionsFor(makeServiceTask('slack/PostMessage'));
    expect(slackOptions.map((o: any) => o.value)).toEqual(['', 'slack-team']);
  });

  it('omits inactive profiles so a deactivated one cannot be picked', () => {
    primeConnectorProfiles(
      [smtpTemplate()],
      [
        profile({ id: '1', profile_name: 'live' }),
        profile({ id: '2', profile_name: 'retired', is_active: false }),
      ],
    );

    const options = optionsFor(makeServiceTask('smtp/SendHTMLEmail'));
    expect(options.map((o: any) => o.value)).toEqual(['', 'live']);
  });

  it('offers only the empty choice when no profile has been saved yet', () => {
    primeConnectorProfiles([smtpTemplate()], []);
    const options = optionsFor(makeServiceTask('smtp/SendHTMLEmail'));
    expect(options).toEqual([expect.objectContaining({ value: '' })]);
  });
});

describe('ConnectorProfileSelect read and write', () => {
  function entryFor(element: any, executed: any[] = []) {
    const entry: any = ConnectorProfileSelect({
      element,
      commandStack: { execute: (...args: any[]) => executed.push(args) },
      moddle,
      translate: (s: string) => s,
    });
    return entry.__selectEntry;
  }

  it('writes the profile name as a quoted python expression', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail', [{ id: 'smtp_host' }]);
    const executed: any[] = [];

    entryFor(element, executed).setValue('smtp-staging');

    const written = element.__operator.parameterList.parameters.find(
      (p: any) => p.id === PROFILE_PARAMETER_ID,
    );
    // Parameter values are evaluated as python, so a literal must be quoted.
    expect(written.value).toBe('"smtp-staging"');
    expect(executed).toHaveLength(1);
  });

  it('reads back the value it wrote', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail');

    entryFor(element).setValue('smtp-staging');

    expect(entryFor(element).getValue()).toBe('smtp-staging');
  });

  it('blanks the parameters the profile supplies, leaving the rows in place', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: 'smtp_host', value: '"smtp.old"' },
      { id: 'smtp_password', value: '"M8FLOW_SECRET:SMTP_PASSWORD"' },
      { id: 'email_to', value: 'user_email' },
    ]);

    entryFor(element).setValue('smtp-staging');

    const byId = Object.fromEntries(
      element.__operator.parameterList.parameters.map((p: any) => [p.id, p.value]),
    );
    // No credential is left behind in the diagram...
    expect(byId.smtp_host).toBeUndefined();
    expect(byId.smtp_password).toBeUndefined();
    // ...but a task-level value is untouched.
    expect(byId.email_to).toBe('user_email');
    // The rows themselves survive, so clearing the profile brings them back.
    expect(Object.keys(byId)).toContain('smtp_host');
  });

  it('removes the profile parameter when the selection is cleared', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: '"smtp-staging"' },
    ]);

    const entry = entryFor(element);
    entry.setValue('');

    expect(element.__operator.parameterList.parameters.some(
      (parameter: any) => parameter.id === PROFILE_PARAMETER_ID,
    )).toBe(false);
  });

  it('treats a hand-edited unparseable value as no selection', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail', [
      { id: PROFILE_PARAMETER_ID, value: 'some_process_variable' },
    ]);

    expect(entryFor(element).getValue()).toBe('');
  });

  it('creates the parameter list when the operator has none', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const element = makeServiceTask('smtp/SendHTMLEmail');
    element.__operator.parameterList = undefined;

    entryFor(element).setValue('smtp-staging');

    expect(element.__operator.parameterList.parameters).toHaveLength(1);
  });
});

describe('operator changes', () => {
  it('restores the profile when the new operator is the same connector', () => {
    // Upstream's operator dropdown rebuilds parameterList from scratch, dropping
    // the sibling profile parameter. Within one connector the author's choice
    // still holds, so it has to come back or it is silently lost.
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();

    const element = makeServiceTask('smtp/SendHTMLEmail');
    rewrite(provider, element, makeGroups(element));
    ConnectorProfileSelect({
      element,
      commandStack: { execute: () => {} },
      moddle,
      translate: (s: string) => s,
    }).__selectEntry.setValue('smtp-staging');

    // Upstream wipes the list on operator change.
    const switched = makeServiceTask('smtp/SendPlainEmail', [{ id: 'smtp_host' }]);
    rewrite(provider, switched, makeGroups(switched));

    const restored = switched.__operator.parameterList.parameters.find(
      (p: any) => p.id === PROFILE_PARAMETER_ID,
    );
    expect(restored?.value).toBe('"smtp-staging"');
  });

  it('drops the profile when the new operator is a different connector', () => {
    // A profile is connector-specific: an smtp profile cannot supply a slack
    // token, so carrying it across would be meaningless and confusing.
    primeConnectorProfiles([smtpTemplate(), slackTemplate()], [profile({})]);
    const { provider } = instantiate();

    const element = makeServiceTask('smtp/SendHTMLEmail');
    rewrite(provider, element, makeGroups(element));
    ConnectorProfileSelect({
      element,
      commandStack: { execute: () => {} },
      moddle,
      translate: (s: string) => s,
    }).__selectEntry.setValue('smtp-staging');

    const switched = makeServiceTask('slack/PostMessage', [{ id: 'token' }]);
    rewrite(provider, switched, makeGroups(switched));

    expect(
      switched.__operator.parameterList.parameters.some(
        (p: any) => p.id === PROFILE_PARAMETER_ID,
      ),
    ).toBe(false);
  });

  it('does not resurrect a profile the author deliberately cleared', () => {
    primeConnectorProfiles([smtpTemplate()], [profile({})]);
    const { provider } = instantiate();

    const element = makeServiceTask('smtp/SendHTMLEmail');
    rewrite(provider, element, makeGroups(element));
    const entry = ConnectorProfileSelect({
      element,
      commandStack: { execute: () => {} },
      moddle,
      translate: (s: string) => s,
    }).__selectEntry;
    entry.setValue('smtp-staging');
    entry.setValue('');

    const switched = makeServiceTask('smtp/SendPlainEmail', [{ id: 'smtp_host' }]);
    rewrite(provider, switched, makeGroups(switched));

    expect(
      switched.__operator.parameterList.parameters.some(
        (p: any) => p.id === PROFILE_PARAMETER_ID,
      ),
    ).toBe(false);
  });
});
