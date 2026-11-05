import { describe, expect, it } from 'vitest';

import {
  DROPPED_REPLACE_ACTIONS,
  DroppedConstructReplaceMenuProvider,
  droppedConstructReplaceFilterModule,
  omitDroppedReplaceEntries,
} from '../lib/features/droppedConstructCreate';

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
