import { describe, expect, it, vi } from 'vitest';

import { addCallActivityDrilldowns } from '../lib/features/callActivityDrilldown';

function fakeViewer(ids: string[]) {
  const added: { id: string; type: string; html: HTMLButtonElement }[] = [];
  const removed: unknown[] = [];
  const services: Record<string, any> = {
    elementRegistry: { get: (id: string) => (ids.includes(id) ? { id } : undefined) },
    overlays: {
      add: (id: string, type: string, overlay: { html: HTMLButtonElement }) => added.push({ id, type, html: overlay.html }),
      remove: (filter: unknown) => removed.push(filter),
    },
  };
  return { viewer: { get: (name: string) => services[name] }, added, removed };
}

describe('addCallActivityDrilldowns', () => {
  it('adds one arrow per reached call activity that opens its called process', () => {
    const { viewer, added, removed } = fakeViewer(['call', 'set']);
    const onOpen = vi.fn();

    addCallActivityDrilldowns(
      viewer,
      [
        { bpmn_identifier: 'set', called_process_identifier: null },
        { bpmn_identifier: 'call', called_process_identifier: 'Process_child' },
        // A looped call activity has several task rows: still one arrow.
        { bpmn_identifier: 'call', called_process_identifier: 'Process_child' },
        // Not in this diagram (a child's own task): no arrow.
        { bpmn_identifier: 'missing', called_process_identifier: 'Process_other' },
      ],
      { label: 'Open called process', onOpen },
    );

    expect(removed).toEqual([{ type: 'm8flow-call-activity-drilldown' }]);
    expect(added.map(({ id }) => id)).toEqual(['call']);
    const button = added[0].html;
    expect(button.className).toBe('bjs-drilldown');
    expect(button.getAttribute('aria-label')).toBe('Open called process');
    button.click();
    expect(onOpen).toHaveBeenCalledWith('Process_child');
  });
});
