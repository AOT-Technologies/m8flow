import { describe, expect, it } from 'vitest';
import {
  applyTaskStateMarkers,
  isFlowTaken,
  resolveElementStates,
  taskStateLegendModule,
} from '../lib/features/taskState';

describe('resolveElementStates', () => {
  it('maps Spiff states and leaves not-reached states neutral', () => {
    const states = resolveElementStates([
      { bpmn_identifier: 'Start', state: 'COMPLETED' },
      { bpmn_identifier: 'Review', state: 'READY' },
      { bpmn_identifier: 'Sub', state: 'STARTED' },
      { bpmn_identifier: 'Timer', state: 'WAITING' },
      { bpmn_identifier: 'End', state: 'FUTURE' },
      { bpmn_identifier: 'Gw', state: 'LIKELY' },
    ]);
    expect(Object.fromEntries(states)).toEqual({
      Start: 'completed',
      Review: 'ready',
      Sub: 'ready',
      Timer: 'waiting',
    });
  });

  it('keeps the most live state when a loop leaves several rows for one element', () => {
    const states = resolveElementStates([
      { bpmn_identifier: 'Loop', state: 'COMPLETED' },
      { bpmn_identifier: 'Loop', state: 'READY' },
      { bpmn_identifier: 'Loop', state: 'COMPLETED' },
    ]);
    expect(states.get('Loop')).toBe('ready');
  });
});

describe('isFlowTaken', () => {
  it.each([
    ['completed', 'completed', true],
    ['completed', 'ready', true],
    ['completed', 'waiting', true],
    ['completed', 'error', true],
    ['completed', 'cancelled', false],
    ['completed', undefined, false],
    ['ready', 'completed', false],
    [undefined, 'ready', false],
  ] as const)('%s -> %s is %s', (source, target, expected) => {
    expect(isFlowTaken(source, target)).toBe(expected);
  });
});

describe('applyTaskStateMarkers', () => {
  function fakeViewer(elements: any[]) {
    const markers: [string, string][] = [];
    const byId = new Map(elements.map((element) => [element.id, element]));
    const services: Record<string, unknown> = {
      canvas: { addMarker: (id: string, className: string) => markers.push([id, className]) },
      elementRegistry: {
        get: (id: string) => byId.get(id),
        filter: (fn: (element: any) => boolean) => elements.filter(fn),
      },
    };
    return { viewer: { get: (name: string) => services[name] }, markers };
  }

  it('marks reached elements, highlights only taken flows, skips unknown ids', () => {
    const start = { id: 'Start', type: 'bpmn:StartEvent' };
    const review = { id: 'Review', type: 'bpmn:UserTask' };
    const end = { id: 'End', type: 'bpmn:EndEvent' };
    const { viewer, markers } = fakeViewer([
      start,
      review,
      end,
      { id: 'F1', type: 'bpmn:SequenceFlow', source: start, target: review },
      { id: 'F2', type: 'bpmn:SequenceFlow', source: review, target: end },
    ]);

    applyTaskStateMarkers(viewer, [
      { bpmn_identifier: 'Start', state: 'COMPLETED' },
      { bpmn_identifier: 'Review', state: 'READY' },
      { bpmn_identifier: 'End', state: 'FUTURE' },
      { bpmn_identifier: 'Missing', state: 'COMPLETED' },
    ]);

    expect(markers).toEqual([
      ['Start', 'm8flow-bpmn-task-completed'],
      ['Review', 'm8flow-bpmn-task-ready'],
      ['F1', 'm8flow-bpmn-flow-taken'],
    ]);
  });
});

describe('task state legend', () => {
  it('shows a swatch per state plus not-reached and path-taken rows', () => {
    const container = document.createElement('div');
    const Legend = taskStateLegendModule.m8flowTaskStateLegend[1] as any;
    new Legend({ getContainer: () => container }, { on() {} });

    const rows = Array.from(container.querySelectorAll('.m8flow-bpmn-legend-row')).map((row) => row.textContent);
    expect(rows).toEqual(['Completed', 'Ready', 'Waiting', 'Error', 'Cancelled', 'Not reached', 'Path taken']);
    const swatches = Array.from(container.querySelectorAll('.m8flow-bpmn-legend-swatch')).map((s) => s.className);
    expect(swatches).toEqual([
      'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-completed',
      'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-ready',
      'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-waiting',
      'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-error',
      'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-cancelled',
      'm8flow-bpmn-legend-swatch',
    ]);
  });
});
