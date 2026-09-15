/**
 * Custom BPMN palette: the old bpmn-js set **minus data store**.
 *
 * Replaces bpmn-js's PaletteProvider via the same `paletteProvider` DI key
 * (see `Modeler.ts` `_m8flowModules`). Keep-scope entries match stock
 * PaletteProvider: tools (hand, lasso, space, connect), events (start,
 * intermediate, end), gateway, task, data object, expanded subprocess,
 * participant, group. `create.data-store` is omitted — data-store persist
 * is dropped; the replace-menu back-door is stripped in
 * `droppedConstructCreate.ts` so pad and palette agree.
 *
 * Drag/click-to-place uses the same create.start()/elementFactory contract
 * as stock bpmn-js. Visual chrome lives in diagram-chrome.css.
 */
export const KEEP_SCOPE_PALETTE_ACTIONS = [
  'hand-tool',
  'lasso-tool',
  'space-tool',
  'global-connect-tool',
  'create.start-event',
  'create.intermediate-event',
  'create.end-event',
  'create.exclusive-gateway',
  'create.task',
  'create.data-object',
  'create.subprocess-expanded',
  'create.participant-expanded',
  'create.group',
] as const;

export const DROPPED_PALETTE_ACTIONS = ['create.data-store'] as const;

export function CustomPaletteProvider(
  this: any,
  palette: any,
  create: any,
  elementFactory: any,
  spaceTool: any,
  lassoTool: any,
  handTool: any,
  globalConnect: any,
  translate: any,
) {
  this._create = create;
  this._elementFactory = elementFactory;
  this._spaceTool = spaceTool;
  this._lassoTool = lassoTool;
  this._handTool = handTool;
  this._globalConnect = globalConnect;
  this._translate = translate;

  palette.registerProvider(this);
}

(CustomPaletteProvider as any).$inject = [
  'palette',
  'create',
  'elementFactory',
  'spaceTool',
  'lassoTool',
  'handTool',
  'globalConnect',
  'translate',
];

CustomPaletteProvider.prototype.getPaletteEntries = function getPaletteEntries(this: any) {
  const {
    _create: create,
    _elementFactory: elementFactory,
    _spaceTool: spaceTool,
    _lassoTool: lassoTool,
    _handTool: handTool,
    _globalConnect: globalConnect,
    _translate: translate,
  } = this;

  function createAction(type: string, group: string, className: string, title: string) {
    function createListener(event: unknown) {
      const shape = elementFactory.createShape({ type });
      create.start(event, shape);
    }
    return {
      group,
      className,
      title,
      action: { dragstart: createListener, click: createListener },
    };
  }

  function createSubprocess(event: unknown) {
    const subProcess = elementFactory.createShape({
      type: 'bpmn:SubProcess',
      x: 0,
      y: 0,
      isExpanded: true,
    });
    const startEvent = elementFactory.createShape({
      type: 'bpmn:StartEvent',
      x: 40,
      y: 82,
      parent: subProcess,
    });
    create.start(event, [subProcess, startEvent], {
      hints: { autoSelect: [subProcess] },
    });
  }

  function createParticipant(event: unknown) {
    create.start(event, elementFactory.createParticipantShape());
  }

  return {
    'hand-tool': {
      group: 'tools',
      className: 'bpmn-icon-hand-tool',
      title: translate('Activate hand tool'),
      action: { click: (event: unknown) => handTool.activateHand(event) },
    },
    'lasso-tool': {
      group: 'tools',
      className: 'bpmn-icon-lasso-tool',
      title: translate('Activate lasso tool'),
      action: { click: (event: unknown) => lassoTool.activateSelection(event) },
    },
    'space-tool': {
      group: 'tools',
      className: 'bpmn-icon-space-tool',
      title: translate('Activate create/remove space tool'),
      action: { click: (event: unknown) => spaceTool.activateSelection(event) },
    },
    'global-connect-tool': {
      group: 'tools',
      className: 'bpmn-icon-connection-multi',
      title: translate('Activate global connect tool'),
      action: { click: (event: unknown) => globalConnect.start(event) },
    },
    'tool-separator': {
      group: 'tools',
      separator: true,
    },
    'create.start-event': createAction(
      'bpmn:StartEvent',
      'event',
      'bpmn-icon-start-event-none',
      translate('Create start event'),
    ),
    'create.intermediate-event': createAction(
      'bpmn:IntermediateThrowEvent',
      'event',
      'bpmn-icon-intermediate-event-none',
      translate('Create intermediate/boundary event'),
    ),
    'create.end-event': createAction(
      'bpmn:EndEvent',
      'event',
      'bpmn-icon-end-event-none',
      translate('Create end event'),
    ),
    'create.exclusive-gateway': createAction(
      'bpmn:ExclusiveGateway',
      'gateway',
      'bpmn-icon-gateway-none',
      translate('Create gateway'),
    ),
    'create.task': createAction('bpmn:Task', 'activity', 'bpmn-icon-task', translate('Create task')),
    'create.data-object': createAction(
      'bpmn:DataObjectReference',
      'data-object',
      'bpmn-icon-data-object',
      translate('Create data object reference'),
    ),
    'create.subprocess-expanded': {
      group: 'activity',
      className: 'bpmn-icon-subprocess-expanded',
      title: translate('Create expanded sub-process'),
      action: { dragstart: createSubprocess, click: createSubprocess },
    },
    'create.participant-expanded': {
      group: 'collaboration',
      className: 'bpmn-icon-participant',
      title: translate('Create pool/participant'),
      action: { dragstart: createParticipant, click: createParticipant },
    },
    'create.group': createAction('bpmn:Group', 'artifact', 'bpmn-icon-group', translate('Create group')),
  };
};

export const customPaletteModule = {
  __init__: ['paletteProvider'],
  paletteProvider: ['type', CustomPaletteProvider],
};
