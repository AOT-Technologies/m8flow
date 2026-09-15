/**
 * Task-state markers + legend for the process instance NavigatedViewer.
 */
import '../assets/task-state.css';

export type BpmnInstanceTask = {
  bpmn_identifier: string;
  state: string;
};

const STATE_MARKER_CLASS: Record<string, string> = {
  COMPLETED: 'm8flow-bpmn-task-completed',
  ERROR: 'm8flow-bpmn-task-error',
  WAITING: 'm8flow-bpmn-task-waiting',
  READY: 'm8flow-bpmn-task-ready',
  CANCELLED: 'm8flow-bpmn-task-cancelled',
  TERMINATED: 'm8flow-bpmn-task-cancelled',
};

const LEGEND: { label: string; colorVar: string }[] = [
  { label: 'Completed', colorVar: '--color-success' },
  { label: 'Ready', colorVar: '--color-info' },
  { label: 'Waiting', colorVar: '--color-warning' },
  { label: 'Error', colorVar: '--color-destructive' },
  { label: 'Cancelled', colorVar: '--color-muted-foreground' },
];

export function applyTaskStateMarkers(viewer: any, tasks: BpmnInstanceTask[]) {
  const canvas = viewer.get('canvas');
  const elementRegistry = viewer.get('elementRegistry');
  for (const task of tasks) {
    const className = STATE_MARKER_CLASS[task.state];
    if (!className) continue;
    if (!elementRegistry.get(task.bpmn_identifier)) continue;
    try {
      canvas.addMarker(task.bpmn_identifier, className);
    } catch {
      /* skip missing shapes */
    }
  }
}

function TaskStateLegend(this: any, canvas: any, eventBus: any) {
  const parent = canvas.getContainer();
  parent.classList.add('m8flow-bpmn');

  const root = document.createElement('div');
  root.className = 'm8flow-bpmn-legend';
  root.innerHTML = [
    '<div class="m8flow-bpmn-legend-title">Task state</div>',
    ...LEGEND.map(
      (item) =>
        `<div class="m8flow-bpmn-legend-row"><span class="m8flow-bpmn-legend-swatch" style="border-color: var(${item.colorVar})"></span>${item.label}</div>`,
    ),
  ].join('');

  parent.appendChild(root);
  eventBus.on('diagram.destroy', () => root.remove());
}

(TaskStateLegend as any).$inject = ['canvas', 'eventBus'];

export const taskStateLegendModule = {
  __init__: ['m8flowTaskStateLegend'],
  m8flowTaskStateLegend: ['type', TaskStateLegend],
};
