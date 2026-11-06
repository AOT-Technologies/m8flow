/**
 * Process-instance drill-down into a call activity's child process: the same
 * ↗ button the modeler shows (bpmn-js-spiffworkflow CallActivityInterceptor),
 * on every call activity this instance reached. Always shown, not only on
 * selection: in the instance view a click on the shape opens its task dialog.
 */
const OVERLAY_TYPE = 'm8flow-call-activity-drilldown';

// Same icon as CallActivityInterceptor; constant markup, no user data.
const ARROW_SVG =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
  '<rect width="24" height="24" fill="#2196f3"/>' +
  '<path d="M7 17L17 7M17 7H8M17 7V16" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>' +
  '</svg>';

export type CalledProcessTask = {
  bpmn_identifier: string;
  called_process_identifier?: string | null;
};

export function addCallActivityDrilldowns(
  viewer: any,
  tasks: CalledProcessTask[],
  { label, onOpen }: { label: string; onOpen: (processId: string) => void },
) {
  const overlays = viewer.get('overlays');
  const elementRegistry = viewer.get('elementRegistry');
  overlays.remove({ type: OVERLAY_TYPE });

  const calledByElement = new Map<string, string>();
  for (const task of tasks) {
    if (task.called_process_identifier) calledByElement.set(task.bpmn_identifier, task.called_process_identifier);
  }

  calledByElement.forEach((processId, elementId) => {
    if (!elementRegistry.get(elementId)) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'bjs-drilldown';
    button.title = label;
    button.setAttribute('aria-label', label);
    button.innerHTML = ARROW_SVG;
    button.addEventListener('click', () => onOpen(processId));
    overlays.add(elementId, OVERLAY_TYPE, { position: { bottom: -10, right: -8 }, html: button });
  });
}
