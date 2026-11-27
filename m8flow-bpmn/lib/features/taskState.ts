/**
 * Task-state markers, taken-path flows, and legend for the
 * process instance NavigatedViewer.
 *
 * each state pairs colour with stroke weight, fill tint, glow or
 * dash. Not-reached states (FUTURE/LIKELY/MAYBE) get nothing, so they keep
 * the renderer's neutral look.
 */
import { isAny } from 'bpmn-js/lib/util/ModelUtil';
import '../assets/task-state.css';
import { CHEVRON_UP_PATHS, svgIcon } from './svgIcon';

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

// Swatches mirror the diagram's .m8flow-bpmn-task-* styles (task-state.css).
const LEGEND_ROWS: { swatch: string; label: string }[] = [
  { swatch: 'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-completed', label: 'Completed' },
  { swatch: 'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-ready', label: 'Ready' },
  { swatch: 'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-waiting', label: 'Waiting' },
  { swatch: 'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-error', label: 'Error' },
  { swatch: 'm8flow-bpmn-legend-swatch m8flow-bpmn-legend-swatch-cancelled', label: 'Cancelled' },
  { swatch: 'm8flow-bpmn-legend-swatch', label: 'Not reached' },
  { swatch: 'm8flow-bpmn-legend-swatch-path', label: 'Path taken' },
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

function TaskStateLegend(this: any, canvas: any, eventBus: any, translate: (template: string) => string) {
  const parent = canvas.getContainer();
  parent.classList.add('m8flow-bpmn');

  const root = document.createElement('div');
  root.className = 'm8flow-bpmn-legend';
  // Open by default; the title doubles as the minimize toggle.
  let collapsed = false;

  // textContent, not innerHTML: labels come from translators. Re-run on
  // i18n.changed so a language switch reaches an open diagram.
  const render = () => {
    const title = document.createElement('button');
    title.type = 'button';
    title.className = 'm8flow-bpmn-legend-title';
    title.title = translate(collapsed ? 'Expand' : 'Minimize');
    title.setAttribute('aria-expanded', String(!collapsed));
    const label = document.createElement('span');
    label.textContent = translate('Task state');
    title.append(label);
    title.append(svgIcon(CHEVRON_UP_PATHS, 14, 'm8flow-bpmn-legend-chevron'));
    title.addEventListener('click', () => {
      collapsed = !collapsed;
      render();
    });
    root.classList.toggle('m8flow-bpmn-legend--collapsed', collapsed);
    const rows = LEGEND_ROWS.map(({ swatch, label }) => {
      const row = document.createElement('div');
      row.className = 'm8flow-bpmn-legend-row';
      const span = document.createElement('span');
      span.className = swatch;
      row.append(span, translate(label));
      return row;
    });
    root.replaceChildren(title, ...rows);
  };
  render();
  eventBus.on('i18n.changed', render);

  // Expanded view (zoomControls). Runs only when the view enters or leaves
  // expanded mode, not on the user's own toggle clicks:
  // - entering: remember the current state, then minimize so the legend
  //   doesn't cover the diagram (the user can still reopen it);
  // - leaving: restore the state from *before* expanding. Changes made while
  //   expanded do not carry over to the normal view.
  let collapsedBeforeExpand = false;
  eventBus.on('m8flow.expand.changed', ({ expanded }: { expanded: boolean }) => {
    if (expanded) collapsedBeforeExpand = collapsed;
    collapsed = expanded || collapsedBeforeExpand;
    render();
  });

  parent.appendChild(root);
  eventBus.on('diagram.destroy', () => root.remove());
}

(TaskStateLegend as any).$inject = ['canvas', 'eventBus', 'translate'];

export const taskStateLegendModule = {
  __init__: ['m8flowTaskStateLegend'],
  m8flowTaskStateLegend: ['type', TaskStateLegend],
};
