import BpmnModdle from 'bpmn-moddle';
import { describe, expect, it, vi } from 'vitest';

import {
  DROPPED_REPLACE_ACTIONS,
  DroppedConstructReplaceMenuProvider,
  droppedConstructReplaceFilterModule,
  omitDroppedReplaceEntries,
} from '../lib/features/droppedConstructCreate';
import {
  DROPPED_CONSTRUCT_NOTICE_GROUP_ID,
  DroppedConstructPanelProvider,
} from '../lib/features/droppedConstructPanel';

describe('omitDroppedReplaceEntries', () => {
  it('strips dropped morphs and keeps call activity (M8F-668)', () => {
    const entries = {
      'replace-with-data-store-reference': { label: 'Data store' },
      'replace-with-call-activity': { label: 'Call activity' },
      'replace-with-message-start': { label: 'Message start' },
      'replace-with-event-subprocess': { label: 'Event sub-process' },
      'replace-with-task': { label: 'Task' },
    };
    expect(omitDroppedReplaceEntries(entries)).toEqual({
      'replace-with-call-activity': { label: 'Call activity' },
      'replace-with-task': { label: 'Task' },
    });
    expect(DROPPED_REPLACE_ACTIONS).not.toContain('replace-with-call-activity');
    expect(DROPPED_REPLACE_ACTIONS).toContain('replace-with-compensation-start');
  });

  it('returns the same object when nothing dropped is present', () => {
    const entries = { 'replace-with-task': { label: 'Task' } };
    expect(omitDroppedReplaceEntries(entries)).toBe(entries);
  });

  it('passes through empty/missing menus', () => {
    expect(omitDroppedReplaceEntries(undefined)).toBeUndefined();
    expect(omitDroppedReplaceEntries(null)).toBeNull();
  });
});

describe('droppedConstructReplaceFilterModule', () => {
  it('replaces stock replaceMenuProvider the same way the palette override works', () => {
    expect(droppedConstructReplaceFilterModule.__init__).toEqual(['replaceMenuProvider']);
    expect(droppedConstructReplaceFilterModule.replaceMenuProvider).toEqual([
      'type',
      DroppedConstructReplaceMenuProvider,
    ]);
    expect((DroppedConstructReplaceMenuProvider as { $inject: string[] }).$inject).toEqual(
      expect.arrayContaining(['popupMenu', 'bpmnReplace', 'translate']),
    );
  });
});

describe('compensation authoring', () => {
  const moddle = new BpmnModdle();
  const translate = (label: string) => label;

  function providers() {
    const replaceElement = vi.fn();
    const menu = new (DroppedConstructReplaceMenuProvider as any)(
      undefined, { registerProvider: vi.fn() }, undefined, moddle,
      { replaceElement }, { allowed: () => true }, translate,
    );
    const panel = new (DroppedConstructPanelProvider as any)({ registerProvider: vi.fn() }, translate);
    return { menu, panel, replaceElement };
  }

  it.each([
    ['bpmn:BoundaryEvent', 'replace-with-compensation-boundary'],
    ['bpmn:IntermediateThrowEvent', 'replace-with-compensation-intermediate-throw'],
    ['bpmn:EndEvent', 'replace-with-compensation-end'],
  ])('offers a compensation replacement and retains its properties for %s', (type, actionId) => {
    const { menu, panel, replaceElement } = providers();
    const businessObject = moddle.create(type);
    if (type === 'bpmn:BoundaryEvent') {
      businessObject.attachedToRef = moddle.create('bpmn:UserTask');
    }
    const target = { type, businessObject };
    const entries = menu.getPopupMenuEntries(target);

    expect(entries[actionId]).toBeDefined();
    entries[actionId].action();
    expect(replaceElement).toHaveBeenCalledWith(target, expect.objectContaining({
      type,
      eventDefinitionType: 'bpmn:CompensateEventDefinition',
    }));

    businessObject.eventDefinitions = [moddle.create('bpmn:CompensateEventDefinition')];
    const groups = panel.getGroups(target)([{ id: 'general' }, { id: 'compensation' }]);
    expect(groups.map((group: { id: string }) => group.id)).toEqual(['general', 'compensation']);
  });

  it('keeps compensation start events unavailable and labels imported starts unsupported', () => {
    const { menu, panel } = providers();
    const businessObject = moddle.create('bpmn:StartEvent');
    businessObject.$parent = moddle.create('bpmn:SubProcess', { triggeredByEvent: true });
    const target = { type: 'bpmn:StartEvent', businessObject };
    expect(menu.getPopupMenuEntries(target)).not.toHaveProperty('replace-with-compensation-start');

    businessObject.eventDefinitions = [moddle.create('bpmn:CompensateEventDefinition')];
    const groups = panel.getGroups(target)([{ id: 'general' }]);
    expect(groups).toContainEqual(expect.objectContaining({ id: DROPPED_CONSTRUCT_NOTICE_GROUP_ID }));
  });

  it('offers cancel end and boundary replacements in transaction context', () => {
    const { menu } = providers();
    const transaction = moddle.create('bpmn:Transaction');
    const end = moddle.create('bpmn:EndEvent');
    end.$parent = transaction;
    const boundary = moddle.create('bpmn:BoundaryEvent', { attachedToRef: transaction });

    expect(menu.getPopupMenuEntries({ businessObject: end })).toHaveProperty('replace-with-cancel-end');
    expect(menu.getPopupMenuEntries({ businessObject: boundary })).toHaveProperty('replace-with-cancel-boundary');

    end.$parent = moddle.create('bpmn:Process');
    boundary.attachedToRef = moddle.create('bpmn:UserTask');
    expect(menu.getPopupMenuEntries({ businessObject: end })).not.toHaveProperty('replace-with-cancel-end');
    expect(menu.getPopupMenuEntries({ businessObject: boundary })).not.toHaveProperty('replace-with-cancel-boundary');
  });
});
