/**
 * Modeler helpers that used to live in designer BpmnCanvas — package-owned
 * distribution behavior (camunda-bpmn-js style), not host React.
 */

const LOOP_DATA_REF_PROPS = new Set(['bpmn:loopDataInputRef', 'bpmn:loopDataOutputRef']);

export function fixUnresolvedReferences(modeler: any) {
  modeler.on('import.parse.complete', (event: any) => {
    const dangling = (event.references ?? []).filter((ref: any) => LOOP_DATA_REF_PROPS.has(ref.property));
    if (dangling.length === 0) return;

    const moddle = modeler._moddle;
    const descriptor = moddle.registry.getEffectiveDescriptor('bpmn:ItemAwareElement');
    dangling.forEach((ref: any) => {
      const placeholder = moddle.create(descriptor, { id: ref.id });
      placeholder.$parent = ref.element;
      ref.element.set(ref.property, placeholder);
    });
  });
}

export function positionContextPadAboveTarget(modeler: any) {
  const contextPad = modeler.get('contextPad');
  const defaultGetPosition = contextPad._getPosition.bind(contextPad);
  const CONTEXT_PAD_MARGIN = 8;

  contextPad._getPosition = function (target: any) {
    const isMultiSelect = Array.isArray(target);
    const isConnection = !isMultiSelect && Array.isArray(target.waypoints);
    if (isMultiSelect || isConnection) {
      return defaultGetPosition(target);
    }

    const containerBounds = this._canvas.getContainer().getBoundingClientRect();
    const targetBounds = this._getTargetBounds(target);
    const padBounds = this._current.html.getBoundingClientRect();

    return {
      left: targetBounds.left + targetBounds.width / 2 - containerBounds.left - padBounds.width / 2,
      top: targetBounds.top - containerBounds.top - padBounds.height - CONTEXT_PAD_MARGIN,
    };
  };
}

const SCRIPT_ICON_SVG =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h11l5 5v11H4z"/><path d="M15 4v5h5"/></svg>';
const SCRIPT_BADGES: Array<[string, Record<string, number>]> = [
  ['spiffworkflow:PreScript', { bottom: 25, left: 0 }],
  ['spiffworkflow:PostScript', { bottom: 25, right: 25 }],
];

export function createPrePostScriptOverlay(modeler: any, event: any) {
  const element = event.element;
  if (!element || element.type === 'bpmn:ScriptTask') return;

  const extensions = element.businessObject?.extensionElements?.values ?? [];
  const overlays = modeler.get('overlays');

  SCRIPT_BADGES.forEach(([extensionType, position]) => {
    const script = extensions.find((ext: any) => ext.$type === extensionType);
    if (script?.value) {
      overlays.add(element.id, { position, html: SCRIPT_ICON_SVG });
    }
  });
}
