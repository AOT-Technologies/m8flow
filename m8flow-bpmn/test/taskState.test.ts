import { describe, expect, it } from 'vitest';
import { applyTaskStateMarkers } from '../lib/features/taskState';

describe('applyTaskStateMarkers', () => {
  it('adds marker classes for known Spiff states', () => {
    const markers = new Map();
    const viewer = {
      get(name: string) {
        if (name === 'canvas') {
          return {
            addMarker(id: string, className: string) {
              markers.set(id, className);
            },
          };
        }
        if (name === 'elementRegistry') {
          return {
            get(id: string) {
              return id === 'Task_1' ? { id } : undefined;
            },
          };
        }
        throw new Error(`unexpected service ${name}`);
      },
    };

    applyTaskStateMarkers(viewer, [
      { bpmn_identifier: 'Task_1', state: 'COMPLETED' },
      { bpmn_identifier: 'Missing', state: 'READY' },
      { bpmn_identifier: 'Task_1', state: 'UNKNOWN' },
    ]);

    expect(markers.get('Task_1')).toBe('m8flow-bpmn-task-completed');
    expect(markers.size).toBe(1);
  });
});
