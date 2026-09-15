import { describe, expect, it } from 'vitest';

import {
  DROPPED_CONSTRUCT_NOTICE_GROUP_ID,
  classifyDroppedConstruct,
  stripDroppedPanelGroups,
} from '../lib/features/droppedConstructPanel';

describe('classifyDroppedConstruct', () => {
  it('classifies call activity, data store, and event subprocess', () => {
    expect(classifyDroppedConstruct({ type: 'bpmn:CallActivity' })).toBe('callActivity');
    expect(classifyDroppedConstruct({ type: 'bpmn:DataStoreReference' })).toBe('dataStore');
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:SubProcess',
        businessObject: { triggeredByEvent: true },
      }),
    ).toBe('eventSubprocess');
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:SubProcess',
        businessObject: { triggeredByEvent: false },
      }),
    ).toBeNull();
  });

  it('classifies multi-instance, message events, and compensation events', () => {
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:UserTask',
        businessObject: { loopCharacteristics: { $type: 'bpmn:MultiInstanceLoopCharacteristics' } },
      }),
    ).toBe('multiInstance');
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:StartEvent',
        businessObject: { eventDefinitions: [{ $type: 'bpmn:MessageEventDefinition' }] },
      }),
    ).toBe('message');
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:EndEvent',
        businessObject: { eventDefinitions: [{ $type: 'bpmn:CompensateEventDefinition' }] },
      }),
    ).toBe('compensate');
  });

  it('leaves keep-scope elements unclassified', () => {
    expect(classifyDroppedConstruct({ type: 'bpmn:UserTask', businessObject: {} })).toBeNull();
    expect(classifyDroppedConstruct({ type: 'bpmn:SendTask', businessObject: {} })).toBeNull();
    expect(
      classifyDroppedConstruct({
        type: 'bpmn:UserTask',
        businessObject: { loopCharacteristics: { $type: 'bpmn:StandardLoopCharacteristics' } },
      }),
    ).toBeNull();
  });
});

describe('stripDroppedPanelGroups', () => {
  it('strips call-activity, data-store, correlation, and multi-instance groups on a task', () => {
    const groups = [
      { id: 'general' },
      { id: 'called_element' },
      { id: 'custom-datastore-properties' },
      { id: 'correlation_properties' },
      { id: 'multiInstance' },
      { id: 'messages' },
    ];
    expect(stripDroppedPanelGroups(groups, { type: 'bpmn:UserTask', businessObject: {} }).map((g) => g.id)).toEqual([
      'general',
      'messages',
    ]);
  });

  it('strips process-level Messages but keeps Send Task messages', () => {
    const processGroups = [{ id: 'general' }, { id: 'messages' }, { id: 'correlation_properties' }];
    expect(stripDroppedPanelGroups(processGroups, { type: 'bpmn:Process' }).map((g) => g.id)).toEqual(['general']);

    const sendGroups = [{ id: 'general' }, { id: 'messages' }];
    expect(stripDroppedPanelGroups(sendGroups, { type: 'bpmn:SendTask', businessObject: {} }).map((g) => g.id)).toEqual([
      'general',
      'messages',
    ]);
  });

  it('strips the message-event Messages group', () => {
    const groups = [{ id: 'general' }, { id: 'messages' }];
    const element = {
      type: 'bpmn:StartEvent',
      businessObject: { eventDefinitions: [{ $type: 'bpmn:MessageEventDefinition' }] },
    };
    expect(stripDroppedPanelGroups(groups, element).map((g) => g.id)).toEqual(['general']);
  });
});

describe('dropped construct notice group id', () => {
  it('is stable so the panel can replace it in place', () => {
    expect(DROPPED_CONSTRUCT_NOTICE_GROUP_ID).toBe('dropped_construct_notice');
  });
});
