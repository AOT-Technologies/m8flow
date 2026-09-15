/**
 * bpmn-js seams for task auto-sizing (`taskSizing.ts` owns the geometry).
 *
 * 1. `elementFactory.getDefaultSize` — create-time default (same override
 *    pattern as customPalette). bpmn-js checks SubProcess before Task, so
 *    this does not change container/pool defaults.
 * 2. `element.updateLabel` postExecute — UpdateLabelHandler only honors
 *    `newBounds` for external labels / text annotations, so embedded task
 *    labels need our own interceptor. Uses `modeling.resizeShape` so undo
 *    and DI sync stay on the command stack with the label edit.
 *
 * Tasks are not interactively resizable in bpmn-js, so these are the only
 * size paths. Imported diagrams are left alone until a label is edited
 * (avoid dirtying on open).
 */
import inherits from 'inherits-browser';
import ElementFactory from 'bpmn-js/lib/features/modeling/ElementFactory';
import { is } from 'bpmn-js/lib/util/ModelUtil';
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
import TextUtil from 'diagram-js/lib/util/Text';

import {
  TASK_LABEL_PADDING,
  type TextDimensions,
  defaultTaskSize,
  fitTaskSize,
  isSizedTaskType,
  taskHeightForWidth,
  taskIconGutter,
} from './taskSizing';

export function SizedTaskElementFactory(
  this: any,
  ...args: ConstructorParameters<typeof ElementFactory>
) {
  ElementFactory.apply(this, args);
}

inherits(SizedTaskElementFactory, ElementFactory);

(SizedTaskElementFactory as any).$inject = (ElementFactory as any).$inject;

SizedTaskElementFactory.prototype.getDefaultSize = function getDefaultSize(
  this: any,
  element: any,
  di: any,
) {
  // `is()` is subtype-aware — covers UserTask/ServiceTask/… without listing them.
  if (is(element, 'bpmn:Task')) {
    return defaultTaskSize();
  }
  return ElementFactory.prototype.getDefaultSize.call(this, element, di);
};

/** Same text util/style/padding as bpmn-js `renderEmbeddedLabel`. */
export function createTaskLabelMeasurer(textRenderer: any) {
  const style = textRenderer.getDefaultStyle();
  const textUtil = new (TextUtil as any)({ style });

  return function measureText(text: string, width: number): TextDimensions {
    const { width: textWidth, height } = textUtil.getDimensions(text, {
      box: { width, height: taskHeightForWidth(width) },
      style,
      align: 'center-middle',
      padding: TASK_LABEL_PADDING,
    });
    return { width: textWidth, height };
  };
}

export function TaskAutoSizeBehavior(
  this: any,
  eventBus: any,
  modeling: any,
  textRenderer: any,
) {
  CommandInterceptor.call(this, eventBus);

  const measureText = createTaskLabelMeasurer(textRenderer);

  this.postExecute('element.updateLabel', (event: any) => {
    const { element, newLabel } = event.context ?? {};
    if (!element || !isSizedTaskType(element.type)) {
      return;
    }

    const size = fitTaskSize((width) => measureText(newLabel ?? '', width), {
      gutter: taskIconGutter(element.type),
    });
    if (size.width === element.width && size.height === element.height) {
      return;
    }

    // Resize about centre so mid-point sequence-flow anchors do not drift.
    modeling.resizeShape(element, {
      x: Math.round(element.x + (element.width - size.width) / 2),
      y: Math.round(element.y + (element.height - size.height) / 2),
      width: size.width,
      height: size.height,
    });
  });
}

inherits(TaskAutoSizeBehavior, CommandInterceptor);

(TaskAutoSizeBehavior as any).$inject = ['eventBus', 'modeling', 'textRenderer'];

export const taskSizingModule = {
  __init__: ['taskAutoSizeBehavior'],
  elementFactory: ['type', SizedTaskElementFactory],
  taskAutoSizeBehavior: ['type', TaskAutoSizeBehavior],
};
