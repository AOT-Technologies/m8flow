import { describe, it, expect, vi } from 'vitest';

// Stub so the test doesn't load the bpmn-js-properties-panel render stack.
vi.mock(
  'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionTextInput',
  () => ({ SpiffExtensionTextInput: function SpiffExtensionTextInputStub() {} }),
);

import ExternalFormPropertiesProvider, {
  EXTERNAL_FORM_GROUP_ID,
  EXTERNAL_FORM_URL_PROP,
} from './ExternalFormPropertiesProvider';

function makeElement(type: string) {
  return {
    businessObject: {
      $instanceOf: (candidate: string) => candidate === type,
    },
  };
}

function instantiate() {
  const registered: Array<{ priority: number; provider: any }> = [];
  const propertiesPanel = {
    registerProvider: (priority: number, provider: any) =>
      registered.push({ priority, provider }),
  };
  const translate = (template: string) => template;
  const moddle = {};
  const commandStack = {};
  const provider: any = new (ExternalFormPropertiesProvider as any)(
    propertiesPanel,
    translate,
    moddle,
    commandStack,
  );
  return { provider, registered, moddle, commandStack };
}

describe('ExternalFormPropertiesProvider', () => {
  it('registers itself as a properties-panel provider', () => {
    const { registered } = instantiate();
    expect(registered).toHaveLength(1);
    expect(typeof registered[0].provider.getGroups).toBe('function');
  });

  it('adds a single "Web Form (External Form)" URL group to user tasks', () => {
    const { provider, moddle, commandStack } = instantiate();
    const element = makeElement('bpmn:UserTask');

    const groups = provider.getGroups(element)([]);

    expect(groups).toHaveLength(1);
    const [group] = groups;
    expect(group.id).toBe(EXTERNAL_FORM_GROUP_ID);
    expect(group.label).toBe('Web Form (External Form)');

    expect(group.entries).toHaveLength(1);
    const [urlEntry] = group.entries;
    expect(urlEntry.name).toBe(EXTERNAL_FORM_URL_PROP);
    expect(urlEntry.name).toBe('externalFormUrl');
    expect(urlEntry.id).toBe('extension_externalFormUrl');
    expect(urlEntry.element).toBe(element);
    expect(urlEntry.moddle).toBe(moddle);
    expect(urlEntry.commandStack).toBe(commandStack);
    expect(typeof urlEntry.component).toBe('function');
  });

  it('does not add the group to non-user-task elements', () => {
    const { provider } = instantiate();
    for (const type of [
      'bpmn:ServiceTask',
      'bpmn:ManualTask',
      'bpmn:ScriptTask',
      'bpmn:Task',
    ]) {
      const groups = provider.getGroups(makeElement(type))([]);
      expect(groups).toHaveLength(0);
    }
  });

  it('inserts the group directly below the "Web Form (with Json Schemas)" group', () => {
    const { provider } = instantiate();
    const incoming = [
      { id: 'general' },
      { id: 'spiff_pre_post_scripts' },
      { id: 'user_task_properties' },
      { id: 'instructions' },
      { id: 'allow_guest_user' },
    ];
    const groups = provider.getGroups(makeElement('bpmn:UserTask'))(incoming);

    const ids = groups.map((g: any) => g.id);
    const jsonSchemaIndex = ids.indexOf('user_task_properties');
    expect(ids[jsonSchemaIndex + 1]).toBe(EXTERNAL_FORM_GROUP_ID);
    expect(ids).toEqual([
      'general',
      'spiff_pre_post_scripts',
      'user_task_properties',
      EXTERNAL_FORM_GROUP_ID,
      'instructions',
      'allow_guest_user',
    ]);
  });

  it('appends at the end when the Json Schemas group is absent', () => {
    const { provider } = instantiate();
    const existing = { id: 'pre_existing_group' };
    const groups = provider.getGroups(makeElement('bpmn:UserTask'))([existing]);
    expect(groups[0]).toBe(existing);
    expect(groups[groups.length - 1].id).toBe(EXTERNAL_FORM_GROUP_ID);
    expect(groups).toHaveLength(2);
  });
});
