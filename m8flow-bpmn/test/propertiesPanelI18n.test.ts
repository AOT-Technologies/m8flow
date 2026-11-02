import { h } from 'preact';
import { describe, expect, it, vi } from 'vitest';

import { propertiesPanelI18nModule } from '../lib/features/propertiesPanelI18n';

function mount(translate: (template: string) => string = (template) => template) {
  const handlers: Record<string, () => void> = {};
  const eventBus = {
    on: (event: string, handler: () => void) => {
      handlers[event] = handler;
    },
    fire: vi.fn(),
  };
  const providers: Array<{ priority: number; provider: any }> = [];
  const propertiesPanel = { registerProvider: (priority: number, provider: any) => providers.push({ priority, provider }) };
  const Refresh = propertiesPanelI18nModule.m8flowPropertiesPanelI18n[1] as any;
  new Refresh(eventBus, propertiesPanel, translate);
  return { handlers, eventBus, providers };
}

describe('propertiesPanelI18nModule', () => {
  it('re-renders the properties panel when the language changes', () => {
    const { handlers, eventBus } = mount();

    handlers['i18n.changed']();

    expect(eventBus.fire).toHaveBeenCalledWith('propertiesPanel.providersChanged');
  });

  it('translates group headers last, including ones upstream providers leave raw', () => {
    const dictionary: Record<string, string> = { Signals: 'Signale', General: 'Allgemein' };
    const { providers } = mount((template) => dictionary[template] ?? template);
    const [{ priority, provider }] = providers;
    const groups = [{ id: 'signals', label: 'Signals' }, { id: 'general', label: 'General' }, { id: 'x', label: 'Allgemein' }, { id: 'y' }];

    const result = provider.getGroups({})(groups);

    expect(priority).toBe(1);
    expect(result).toBe(groups);
    expect(result.map((group: { label?: string }) => group.label)).toEqual(['Signale', 'Allgemein', 'Allgemein', undefined]);
  });
});

describe('propertiesPanelI18nModule entries', () => {
  const dictionary: Record<string, string> = {
    'Guest confirmation': 'Gastbestätigung',
    'Shown after completion.': 'Wird danach angezeigt.',
    'ℹ️ Note': 'ℹ️ Hinweis',
    'Launch Editor': 'Editor öffnen',
  };
  const translate = (template: string) => dictionary[template] ?? template;

  function getGroups(groups: any[]) {
    const { providers } = mount(translate);
    return providers[0].provider.getGroups({})(groups);
  }

  it('translates entry labels and descriptions that upstream passes raw', () => {
    const [group] = getGroups([
      { id: 'g', label: 'G', entries: [{ id: 'e', label: 'Guest confirmation', description: 'Shown after completion.' }] },
    ]);

    expect(group.entries[0]).toMatchObject({ label: 'Gastbestätigung', description: 'Wird danach angezeigt.' });
  });

  it('hands translate to list groups and entries that upstream leaves on the identity fallback', () => {
    const own = (template: string) => `own:${template}`;
    const [listGroup, group] = getGroups([
      { id: 'data', label: 'G', items: [] },
      { id: 'g', label: 'G', entries: [{ id: 'inputs' }, { id: 'kept', translate: own }] },
    ]);

    expect(listGroup.translate).toBe(translate);
    expect(group.entries[0].translate).toBe(translate);
    expect(group.entries[1].translate).toBe(own);
  });

  it('translates entries inside list items, never the item label (user data)', () => {
    const [listGroup] = getGroups([
      {
        id: 'data',
        label: 'G',
        items: [{ id: 'i', label: 'Guest confirmation', entries: [{ id: 'e', label: 'Guest confirmation' }] }],
      },
    ]);

    expect(listGroup.items[0].label).toBe('Guest confirmation');
    expect(listGroup.items[0].entries[0].label).toBe('Gastbestätigung');
  });

  it('translates labels a component sets on the entry it renders', () => {
    const Select = () => null;
    const DataObjectSelect = () => h(Select, { label: 'Guest confirmation', description: 'Shown after completion.' });
    const [group] = getGroups([{ id: 'g', label: 'G', entries: [{ id: 's', component: DataObjectSelect }] }]);

    expect(group.entries[0].component({}).props).toMatchObject({
      label: 'Gastbestätigung',
      description: 'Wird danach angezeigt.',
    });
  });

  it("translates a called TextFieldEntry's Description, never its field value", () => {
    const TextField = () => null;
    const Description = () => null;
    // What TextFieldEntry({ label, description }) returns when Spiff calls it as a function.
    const StateEntry = () =>
      h('div', {}, [
        h(TextField, { id: 's', label: 'Guest confirmation', value: 'Guest confirmation' }),
        h(Description, { forId: 's', value: 'Shown after completion.' }),
      ]);
    const [group] = getGroups([{ id: 'g', label: 'G', entries: [{ id: 's', component: StateEntry }] }]);
    const [field, description] = group.entries[0].component({}).props.children;

    expect(field.props).toMatchObject({ label: 'Gastbestätigung', value: 'Guest confirmation' });
    expect(description.props.value).toBe('Wird danach angezeigt.');
  });

  it('translates static description text, never a value read through getValue', () => {
    const [group] = getGroups([
      {
        id: 'g',
        label: 'G',
        entries: [
          { id: 'info', component: () => null, value: 'ℹ️ Note' },
          { id: 'data', component: () => null, value: 'ℹ️ Note', getValue: () => 'ℹ️ Note' },
        ],
      },
    ]);

    expect(group.entries.map((entry: { value: string }) => entry.value)).toEqual(['ℹ️ Hinweis', 'ℹ️ Note']);
  });

  it('translates the text of a button an entry renders, keeping one wrapper per component', () => {
    const LaunchButton = (props: { id: string }) => h('button', { id: props.id }, 'Launch Editor');
    const Field = () => h('input', { value: 'Launch Editor' });
    const first = getGroups([{ id: 'g', label: 'G', entries: [{ id: 'b', component: LaunchButton }, { id: 'f', component: Field }] }]);
    const { providers } = mount(translate);
    const provider = providers[0].provider;
    const again = provider.getGroups({})([{ id: 'g', label: 'G', entries: [{ id: 'b', component: LaunchButton }] }]);
    const again2 = provider.getGroups({})([{ id: 'g', label: 'G', entries: [{ id: 'b', component: LaunchButton }] }]);

    const button = first[0].entries[0].component({ id: 'x' });
    expect(button.type).toBe('button');
    expect(button.props).toMatchObject({ id: 'x', children: 'Editor öffnen' });
    expect(first[0].entries[1].component({}).props.value).toBe('Launch Editor');
    expect(again[0].entries[0].component).toBe(again2[0].entries[0].component);

    // TextAreaEntry-style output: the inner component gets translate, DOM children never do.
    const Inner = () => null;
    const Own = () => null;
    const own = (template: string) => template;
    const TextAreaLike = () =>
      h('div', {}, [h(Inner, { translate: undefined }), h(Own, { translate: own }), h('span', {}, 'x')]);
    const [textArea] = provider.getGroups({})([{ id: 'g', label: 'G', entries: [{ id: 't', component: TextAreaLike }] }])[0].entries;
    const [inner, kept, span] = textArea.component({}).props.children;
    expect(inner.props.translate).toBe(translate);
    expect(kept.props.translate).toBe(own);
    expect(span.props.translate).toBeUndefined();

    // SpiffExtensionTextArea-style output: the root is the component vnode itself.
    const Wrapped = () => h(Inner, {});
    const [rooted] = provider.getGroups({})([{ id: 'g', label: 'G', entries: [{ id: 'r', component: Wrapped }] }])[0].entries;
    expect(rooted.component({}).props.translate).toBe(translate);

    // An entry object reused across renders keeps the same wrapper, not a wrapper of it.
    const reused = provider.getGroups({})(again);
    expect(reused[0].entries[0].component).toBe(again[0].entries[0].component);
  });
});
