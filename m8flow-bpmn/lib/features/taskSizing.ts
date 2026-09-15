/**
 * Pure sizing math for task shapes. `taskSizingBehavior.ts` owns the bpmn-js
 * seams. Geometry stays here (injected `measureText`) so the fit search is
 * unit-testable without diagram-js's browser-only `getBBox()`.
 *
 * Contract: width:height locked at 2.5:1; floor/default is TASK_MIN_*; longer
 * labels grow both axes up to TASK_MAX_WIDTH; icon-bearing tasks also clear
 * TASK_ICON_GUTTER on each side of a centred label.
 */

export const TASK_ASPECT_RATIO = 2.5;

/** Floor and create-time default (150 / 2.5 = 60). */
export const TASK_MIN_WIDTH = 150;
export const TASK_MIN_HEIGHT = 60;

/** Growth ceiling; past this the label overflows like stock bpmn-js. */
export const TASK_MAX_WIDTH = 600;

export const TASK_GROWTH_STEP = 25;

/** Matches bpmn-js `renderEmbeddedLabel` padding. */
export const TASK_LABEL_PADDING = 7;

/**
 * Left/right clearance so a centred label does not run under the top-left
 * type icon. bpmn-js centres the label across the full width with no icon
 * awareness; icons reach ~x=23 (Chromium client rects — `getBBox` ignores
 * child transforms). 32 = that edge plus ~9px clearance. Generic Task has
 * no icon and uses gutter 0. Clearing a centred label costs the gutter on
 * both sides: `textWidth + 2 * gutter <= width`.
 */
export const TASK_ICON_GUTTER = 32;

/**
 * Task types this feature sizes. Excludes SubProcess/Transaction/CallActivity
 * (containers / dropped construct) — same split bpmn-js uses in getDefaultSize.
 */
export const SIZED_TASK_TYPES = [
  'bpmn:Task',
  'bpmn:UserTask',
  'bpmn:ServiceTask',
  'bpmn:ScriptTask',
  'bpmn:ManualTask',
  'bpmn:BusinessRuleTask',
  'bpmn:SendTask',
  'bpmn:ReceiveTask',
] as const;

const SIZED_TASK_TYPE_SET: ReadonlySet<string> = new Set(SIZED_TASK_TYPES);

/** Sized tasks that draw a type icon (everything except generic Task). */
export const ICON_BEARING_TASK_TYPES = SIZED_TASK_TYPES.filter((type) => type !== 'bpmn:Task');

const ICON_BEARING_TASK_TYPE_SET: ReadonlySet<string> = new Set(ICON_BEARING_TASK_TYPES);

export type TaskSize = { width: number; height: number };
export type TextDimensions = { width: number; height: number };

export function isSizedTaskType(type: string | undefined | null): boolean {
  return typeof type === 'string' && SIZED_TASK_TYPE_SET.has(type);
}

export function taskIconGutter(type: string | undefined | null): number {
  const hasIcon = typeof type === 'string' && ICON_BEARING_TASK_TYPE_SET.has(type);
  return hasIcon ? TASK_ICON_GUTTER : 0;
}

export function taskHeightForWidth(width: number): number {
  return Math.max(TASK_MIN_HEIGHT, Math.round(width / TASK_ASPECT_RATIO));
}

export function defaultTaskSize(): TaskSize {
  return { width: TASK_MIN_WIDTH, height: TASK_MIN_HEIGHT };
}

export function taskWidthCandidates(
  minWidth: number = TASK_MIN_WIDTH,
  maxWidth: number = TASK_MAX_WIDTH,
  step: number = TASK_GROWTH_STEP,
): number[] {
  const widths: number[] = [];
  for (let width = minWidth; width < maxWidth; width += step) {
    widths.push(width);
  }
  widths.push(maxWidth);
  return widths;
}

export type MeasureText = (width: number) => TextDimensions;

/**
 * Smallest on-ratio box that fits the label vertically (with padding) and
 * clears `gutter` on each side of the centred text. Ascending width scan:
 * a wider box is also taller at fixed ratio. Empty label → minimum; nothing
 * fits → capped maxWidth.
 */
export function fitTaskSize(
  measureText: MeasureText,
  options: {
    minWidth?: number;
    maxWidth?: number;
    step?: number;
    padding?: number;
    gutter?: number;
  } = {},
): TaskSize {
  const {
    minWidth = TASK_MIN_WIDTH,
    maxWidth = TASK_MAX_WIDTH,
    step = TASK_GROWTH_STEP,
    padding = TASK_LABEL_PADDING,
    gutter = 0,
  } = options;

  for (const width of taskWidthCandidates(minWidth, maxWidth, step)) {
    const height = taskHeightForWidth(width);
    const text = measureText(width);
    const fitsVertically = text.height <= height - 2 * padding;
    const clearsIcon = text.width + 2 * gutter <= width;
    if (fitsVertically && clearsIcon) {
      return { width, height };
    }
  }

  return { width: maxWidth, height: taskHeightForWidth(maxWidth) };
}
