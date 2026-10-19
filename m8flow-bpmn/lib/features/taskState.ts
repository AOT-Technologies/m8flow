/**
 * Task-state markers, taken-path flows, and legend for the
 * process instance NavigatedViewer.
 *
 * M8F-579: each state pairs colour with stroke weight, fill tint, glow or
 * dash. Not-reached states (FUTURE/LIKELY/MAYBE) get nothing, so they keep
 * the renderer's neutral look.
 */
import { isAny } from 'bpmn-js/lib/util/ModelUtil';
import '../assets/task-state.css';

export type BpmnInstanceTask = {
  bpmn_identifier: string;
  state: string;
};

export type TaskStateKey = 'completed' | 'ready' | 'waiting' | 'error' | 'cancelled';

const STATE_KEY: Record<string, TaskStateKey> = {
  COMPLETED: 'completed',
  READY: 'ready',
  // Deliberately 'ready': 'ready' means "the instance is here now". A STARTED
  // call activity / sub-process holds the current task in its child process.
  // applyTaskStateMarkers ignores STARTED on any other element.
  STARTED: 'ready',
  WAITING: 'waiting',
  ERROR: 'error',
  CANCELLED: 'cancelled',
  TERMINATED: 'cancelled',
};

// Loops and multi-instance leave several rows per element; the most live wins.
const PRECEDENCE: TaskStateKey[] = ['error', 'ready', 'waiting', 'completed', 'cancelled'];

const REACHED = new Set<TaskStateKey>(['completed', 'ready', 'waiting', 'error']);

const LEGEND: { key: TaskStateKey; label: string }[] = [
  { key: 'completed', label: 'Completed' },
  { key: 'ready', label: 'Ready' },
  { key: 'waiting', label: 'Waiting' },
  { key: 'error', label: 'Error' },
  { key: 'cancelled', label: 'Cancelled' },
];

export function resolveElementStates(tasks: BpmnInstanceTask[]): Map<string, TaskStateKey> {
  const states = new Map<string, TaskStateKey>();
  for (const task of tasks) {
    const key = STATE_KEY[task.state];
    if (!key) continue;
    const current = states.get(task.bpmn_identifier);
    if (!current || PRECEDENCE.indexOf(key) < PRECEDENCE.indexOf(current)) {
      states.set(task.bpmn_identifier, key);
    }
  }
  return states;
}

// ponytail: inferred from element states, not Spiff's token path (the payload
// has no parent links). A flow whose target was reached via a different path
// also lights up; add parent task guids to the detail payload if that bites.
export function isFlowTaken(source?: TaskStateKey, target?: TaskStateKey): boolean {
  return source === 'completed' && target !== undefined && REACHED.has(target);
}

export function applyTaskStateMarkers(viewer: any, tasks: BpmnInstanceTask[]) {
  const canvas = viewer.get('canvas');
  const elementRegistry = viewer.get('elementRegistry');
  // Spiff also leaves multi-instance / loop parents STARTED under the element's
  // own id; only sub-workflows count, the rest take state from their child rows.
  const states = resolveElementStates(
    tasks.filter(
      (task) =>
        task.state !== 'STARTED' ||
        isAny(elementRegistry.get(task.bpmn_identifier), ['bpmn:CallActivity', 'bpmn:SubProcess']),
    ),
  );

  states.forEach((key, id) => {
    if (elementRegistry.get(id)) canvas.addMarker(id, `m8flow-bpmn-task-${key}`);
  });

  elementRegistry
    .filter((element: any) => element.type === 'bpmn:SequenceFlow')
    .forEach((flow: any) => {
      if (isFlowTaken(states.get(flow.source?.id), states.get(flow.target?.id))) {
        canvas.addMarker(flow.id, 'm8flow-bpmn-flow-taken');
      }
    });
}

function TaskStateLegend(this: any, canvas: any, eventBus: any) {
  const parent = canvas.getContainer();
  parent.classList.add('m8flow-bpmn');

  const root = document.createElement('div');
  root.className = 'm8flow-bpmn-legend';
  root.innerHTML = [
    '<div class="m8flow-bpmn-legend-title">Task state</div>',
    // Swatches mirror the diagram's .m8flow-bpmn-task-* styles (task-state.css).
    ...LEGEND.map(
      (item) =>
        `<div class="m8flow-bpmn-legend-row"><span class="m8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-${item.key}"></span>${item.label}</div>`,
    ),
    '<div class="m8flow-bpmn-legend-row"><span class="m8flow-bpmn-legend-swatch"></span>Not reached</div>',
    '<div class="m8flow-bpmn-legend-row"><span class="m8flow-bpmn-legend-swatch-path"></span>Path taken</div>',
  ].join('');

  parent.appendChild(root);
  eventBus.on('diagram.destroy', () => root.remove());
}

(TaskStateLegend as any).$inject = ['canvas', 'eventBus'];

export const taskStateLegendModule = {
  __init__: ['m8flowTaskStateLegend'],
  m8flowTaskStateLegend: ['type', TaskStateLegend],
};
