import { describe, expect, it } from 'vitest';

import {
  DROPPED_REPLACE_ACTIONS,
  DROPPED_REPLACE_HEADER_ACTIONS,
  DroppedConstructReplaceMenuProvider,
  droppedConstructReplaceFilterModule,
  omitDroppedReplaceEntries,
  omitDroppedReplaceHeaderEntries,
} from '../lib/features/droppedConstructCreate';

describe('omitDroppedReplaceEntries', () => {
  it('strips every dropped morph, including call activity and message events', () => {
    const entries = {
      'replace-with-data-store-reference': { label: 'Data store' },
      'replace-with-call-activity': { label: 'Call activity' },
      'replace-with-message-start': { label: 'Message start' },
      'replace-with-event-subprocess': { label: 'Event sub-process' },
      'replace-with-task': { label: 'Task' },
    };
    expect(omitDroppedReplaceEntries(entries)).toEqual({
      'replace-with-task': { label: 'Task' },
    });
    expect(DROPPED_REPLACE_ACTIONS).toContain('replace-with-call-activity');
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

describe('omitDroppedReplaceHeaderEntries', () => {
  it('hides inactive multi-instance toggles and keeps standard loop', () => {
    const entries = {
      'toggle-parallel-mi': { active: false },
      'toggle-sequential-mi': { active: false },
      'toggle-loop': { active: false },
    };
    expect(omitDroppedReplaceHeaderEntries(entries)).toEqual({
      'toggle-loop': { active: false },
    });
    expect(DROPPED_REPLACE_HEADER_ACTIONS).toEqual(['toggle-parallel-mi', 'toggle-sequential-mi']);
  });

  it('keeps an already-active multi-instance toggle so it can be turned off', () => {
    const entries = {
      'toggle-parallel-mi': { active: true },
      'toggle-sequential-mi': { active: false },
    };
    expect(omitDroppedReplaceHeaderEntries(entries)).toEqual({
      'toggle-parallel-mi': { active: true },
    });
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
