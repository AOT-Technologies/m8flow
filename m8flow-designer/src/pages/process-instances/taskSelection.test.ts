import { describe, expect, it } from 'vitest';

import type { ProcessInstanceTaskState } from '@/lib/processInstancesApi';
import { latestTaskForElement } from './taskSelection';

function task(guid: string, bpmn_identifier: string, last_state_change: number | null): ProcessInstanceTaskState {
  return { guid, bpmn_identifier, bpmn_name: null, typename: 'ScriptTask', state: 'COMPLETED', last_state_change };
}

describe('latestTaskForElement', () => {
  it('picks the most recent run of a looped element', () => {
    const tasks = [task('a', 'Loop_1', 10), task('b', 'Loop_1', 30), task('c', 'Loop_1', 20), task('d', 'Other', 99)];
    expect(latestTaskForElement(tasks, 'Loop_1')?.guid).toBe('b');
  });

  it('returns null for an element with no runtime task (e.g. a lane or sequence flow)', () => {
    expect(latestTaskForElement([task('a', 'Task_1', 1)], 'Flow_1')).toBeNull();
  });
});
