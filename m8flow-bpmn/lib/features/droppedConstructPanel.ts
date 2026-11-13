/**
 * Properties-panel guard for dropped BPMN constructs.
 *
 * Spiff still contributes Messages, Correlation, and Data Store groups.
 * Catalog save 400s those (or the engine rejects data stores). Call
 * activity and multi-instance are supported (M8F-668), so their groups
 * stay. This provider runs *after* those groups are pushed and
 * strips them. If the selected element *is* a leftover dropped shape,
 * it replaces the stripped groups with a short “not supported” notice —
 * hide-or-explain, never a working editor that only fails on save.
 *
 * Process-level Messages / Correlation Properties are stripped with no
 * extra notice (they would otherwise appear on every process click).
 * Send/Receive Task message fields stay: catalog does not reject those
 * task types.
 *
 * No JSX — same Preact `h()` constraint as serviceTaskConnectorPanel.ts.
 */
import { h } from 'preact';

import { removeGroupsById, replaceOrAppendGroup } from './propertiesPanelGroups';

const HIGH_PRIORITY = 2000;
export const DROPPED_CONSTRUCT_NOTICE_GROUP_ID = 'dropped_construct_notice';

export const DROPPED_PANEL_GROUP_IDS = ['correlation_properties', 'custom-datastore-properties'] as const;

/** `messages` is also the Send/Receive Task group — only strip it on
 * process/collaboration (catalog of messages + correlation) and on
 * message *events* (messageEventDefinition). */
const PROCESS_LEVEL_MESSAGE_GROUP_IDS = ['messages'] as const;

export type DroppedConstructKind = 'dataStore' | 'eventSubprocess' | 'message' | 'compensate';

const NOTICE: Record<DroppedConstructKind, string> = {
  dataStore: 'Data stores are not supported in this host.',
  eventSubprocess:
    'Only error, escalation and non-interrupting timer event subprocesses are supported. The catalog rejects other event subprocesses on save.',
  message: 'Message events and correlation are not supported. The catalog rejects this construct on save.',
  compensate: 'Compensation start events are not supported. The catalog rejects this construct on save.',
};

function elementType(element: any): string | undefined {
  return element?.type ?? element?.businessObject?.$type;
}

function hasEventDefinition(element: any, type: string): boolean {
  const definitions = element?.businessObject?.eventDefinitions;
  return Array.isArray(definitions) && definitions.some((definition: any) => definition?.$type === type);
}

/** Mirrors catalog `_event_subprocess_start_supported`: every start event has
 * exactly one definition, either error or escalation (M8F-665) or a timer on a
 * non-interrupting start (M8F-667). The catalog rejects the rest on save. */
function isSupportedEventSubprocess(businessObject: any): boolean {
  const starts = (businessObject?.flowElements ?? []).filter((el: any) => el?.$type === 'bpmn:StartEvent');
  return (
    starts.length > 0 &&
    starts.every((start: any) => {
      const definitions: any[] = start.eventDefinitions ?? [];
      if (definitions.length !== 1) {
        return false;
      }
      const type = definitions[0]?.$type;
      if (type === 'bpmn:ErrorEventDefinition' || type === 'bpmn:EscalationEventDefinition') {
        return true;
      }
      return type === 'bpmn:TimerEventDefinition' && start.isInterrupting === false;
    })
  );
}

export function classifyDroppedConstruct(element: any): DroppedConstructKind | null {
  if (!element) {
    return null;
  }
  const type = elementType(element);
  if (type === 'bpmn:DataStoreReference') {
    return 'dataStore';
  }
  if (
    type === 'bpmn:SubProcess' &&
    element.businessObject?.triggeredByEvent &&
    !isSupportedEventSubprocess(element.businessObject)
  ) {
    return 'eventSubprocess';
  }
  if (hasEventDefinition(element, 'bpmn:MessageEventDefinition')) {
    return 'message';
  }
  if (type === 'bpmn:StartEvent' && hasEventDefinition(element, 'bpmn:CompensateEventDefinition')) {
    return 'compensate';
  }
  return null;
}

function isProcessLevel(element: any): boolean {
  const type = elementType(element);
  return type === 'bpmn:Process' || type === 'bpmn:Collaboration';
}

export function stripDroppedPanelGroups(groups: { id: string }[], element: any): { id: string }[] {
  const ids: string[] = [...DROPPED_PANEL_GROUP_IDS];
  const kind = classifyDroppedConstruct(element);
  if (isProcessLevel(element)) {
    ids.push(...PROCESS_LEVEL_MESSAGE_GROUP_IDS);
  }
  if (kind === 'message') {
    ids.push('messages', 'message');
  }
  return removeGroupsById(groups, ids);
}

function DroppedConstructNotice(props: { text: string }) {
  return h('p', { class: 'bio-properties-panel-description' }, props.text);
}

function createNotSupportedGroup(kind: DroppedConstructKind, translate: (s: string) => string) {
  const text = translate(NOTICE[kind]);
  return {
    id: DROPPED_CONSTRUCT_NOTICE_GROUP_ID,
    label: translate('Not supported'),
    entries: [
      {
        id: 'dropped_construct_notice_text',
        component: function DroppedConstructNoticeEntry() {
          return h(DroppedConstructNotice, { text });
        },
      },
    ],
  };
}

export function DroppedConstructPanelProvider(this: any, propertiesPanel: any, translate: any) {
  this.getGroups = function (element: any) {
    return function (groups: any[]) {
      stripDroppedPanelGroups(groups, element);
      const kind = classifyDroppedConstruct(element);
      if (kind) {
        replaceOrAppendGroup(groups, createNotSupportedGroup(kind, translate));
      }
      return groups;
    };
  };
  propertiesPanel.registerProvider(HIGH_PRIORITY, this);
}

(DroppedConstructPanelProvider as any).$inject = ['propertiesPanel', 'translate'];

export const droppedConstructPanelModule = {
  __init__: ['droppedConstructPanelProvider'],
  droppedConstructPanelProvider: ['type', DroppedConstructPanelProvider],
};
