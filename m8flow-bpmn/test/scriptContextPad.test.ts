import { describe, expect, it, vi } from 'vitest';
import BpmnModdle from 'bpmn-moddle';
import spiffModdleExtension from 'bpmn-js-spiffworkflow/app/spiffworkflow/moddle/spiffworkflow.json';

import { FOCUS_WAIT_MS, ScriptContextPadProvider, scriptContextPadModule } from '../lib/features/scriptContextPad';

const moddle = new BpmnModdle({ spiffworkflow: spiffModdleExtension });

/** A diagram-js-shaped element backed by a real moddle business object. */
function shape(type: string, scripts: Record<string, string> = {}) {
  const values = Object.entries(scripts).map(([scriptType, value]) => moddle.create(scriptType, { value }));
  return {
    businessObject: moddle.create(type, {
      extensionElements: moddle.create('bpmn:ExtensionElements', { values }),
    }),
  };
}

function mountProvider() {
  let priority: number | undefined;
  let provider: any;
  const contextPad = {
    registerProvider(p: number, instance: unknown) {
      priority = p;
      provider = instance;
    },
  };
  const eventBus = { fire: vi.fn() };
  new (ScriptContextPadProvider as any)(contextPad, eventBus, (s: string) => s);
  const entriesFor = (element: unknown, initial: Record<string, any> = {}) =>
    provider.getContextPadEntries(element)({ ...initial });
  return { priority, entriesFor, eventBus };
}

describe('scriptContextPadModule', () => {
  it('registers below spiffworkflow (500) so its pre/post entries are overwritten', () => {
    expect(scriptContextPadModule.__init__).toEqual(['scriptContextPadProvider']);
    expect(mountProvider().priority).toBeLessThan(500);
  });

  it('offers Add entries on a task with no scripts', () => {
    const entries = mountProvider().entriesFor(shape('bpmn:ServiceTask'));
    // Same group as spiffworkflow's own entries, so they share its pad row.
    expect(entries['trigger-preScript']).toMatchObject({ group: 'connect', title: 'Add pre-script' });
    expect(entries['trigger-postScript']).toMatchObject({ group: 'connect', title: 'Add post-script' });
    expect(entries['trigger-preScript'].className).toBeUndefined();
    expect(entries['trigger-postScript'].className).toBeUndefined();
  });

  it('marks only the configured script as Edit + configured', () => {
    const entries = mountProvider().entriesFor(
      shape('bpmn:UserTask', { 'spiffworkflow:PreScript': 'x = 1' }),
    );
    expect(entries['trigger-preScript']).toMatchObject({
      title: 'Edit pre-script',
      className: 'm8flow-script-configured',
    });
    expect(entries['trigger-postScript']).toMatchObject({ title: 'Add post-script' });
    expect(entries['trigger-postScript'].className).toBeUndefined();
  });

  it("replaces spiffworkflow's own teal entry", () => {
    const spiffEntry = { className: 'bpmn-icon-pre-script-trigger', title: 'Open PreScript Editor' };
    const entries = mountProvider().entriesFor(
      shape('bpmn:ServiceTask', { 'spiffworkflow:PreScript': 'x = 1' }),
      { 'trigger-preScript': spiffEntry },
    );
    expect(entries['trigger-preScript'].className).toBe('m8flow-script-configured');
    expect(entries['trigger-preScript'].title).toBe('Edit pre-script');
  });

  it('opens the matching properties-panel textarea on click', () => {
    const { entriesFor, eventBus } = mountProvider();
    const entries = entriesFor(shape('bpmn:ServiceTask'));

    entries['trigger-postScript'].action.click();

    expect(eventBus.fire).toHaveBeenCalledWith('propertiesPanel.showEntry', {
      id: 'pythonScript_spiffworkflow:PostScript',
    });
  });

  it('puts the caret at the end instead of leaving the script selected', async () => {
    const field = document.createElement('textarea');
    field.name = 'pythonScript_spiffworkflow:PreScript';
    field.value = 'x = 1';
    document.body.append(field);
    const { entriesFor } = mountProvider();

    entriesFor(shape('bpmn:ServiceTask', { 'spiffworkflow:PreScript': 'x = 1' }))['trigger-preScript'].action.click();
    // What the panel's showEntry handler does with the field.
    field.focus();
    field.select();
    await new Promise((resolve) => setTimeout(resolve));

    expect([field.selectionStart, field.selectionEnd]).toEqual([5, 5]);
    field.remove();
  });

  it('drops the caret listener when the panel never focuses the field', async () => {
    vi.useFakeTimers();
    const field = document.createElement('textarea');
    field.name = 'pythonScript_spiffworkflow:PreScript';
    field.value = 'x = 1';
    document.body.append(field);
    const { entriesFor } = mountProvider();

    entriesFor(shape('bpmn:ServiceTask'))['trigger-preScript'].action.click();
    await vi.advanceTimersByTimeAsync(FOCUS_WAIT_MS);
    // The user later focuses and selects the field themselves.
    field.focus();
    field.select();
    await vi.runAllTimersAsync();

    expect([field.selectionStart, field.selectionEnd]).toEqual([0, 5]);
    field.remove();
    vi.useRealTimers();
  });

  it('covers call activities and subprocesses, like the Pre/Post Scripts panel group', () => {
    const { entriesFor } = mountProvider();
    expect(entriesFor(shape('bpmn:CallActivity'))).toHaveProperty('trigger-preScript');
    expect(entriesFor(shape('bpmn:SubProcess'))).toHaveProperty('trigger-postScript');
  });

  it('leaves script tasks and non-task elements alone', () => {
    const { entriesFor } = mountProvider();
    const scriptTask = entriesFor(shape('bpmn:ScriptTask'), { 'trigger-script': { title: 'Open Script Editor' } });
    expect(Object.keys(scriptTask)).toEqual(['trigger-script']);
    expect(entriesFor(shape('bpmn:StartEvent'))).toEqual({});
  });
});
