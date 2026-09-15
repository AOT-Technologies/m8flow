import { describe, expect, it } from 'vitest';
import {
  defaultTaskSize,
  fitTaskSize,
  ICON_BEARING_TASK_TYPES,
  isSizedTaskType,
  SIZED_TASK_TYPES,
  TASK_ASPECT_RATIO,
  TASK_GROWTH_STEP,
  TASK_ICON_GUTTER,
  TASK_LABEL_PADDING,
  TASK_MAX_WIDTH,
  TASK_MIN_HEIGHT,
  TASK_MIN_WIDTH,
  taskHeightForWidth,
  taskIconGutter,
  taskWidthCandidates,
} from '../lib/features/taskSizing';

/** Synthetic measurer: wider box → fewer lines; line width capped by usable width. */
function fakeMeasurer(totalTextWidth: number, lineHeight = 14) {
  return (boxWidth: number) => {
    const usable = Math.max(1, boxWidth - 2 * TASK_LABEL_PADDING);
    const lines = Math.ceil(totalTextWidth / usable);
    return { width: Math.min(totalTextWidth, usable), height: lines * lineHeight };
  };
}

describe('shape contract', () => {
  it('holds the 2.5:1 width:height ratio at the minimum size', () => {
    expect(TASK_MIN_WIDTH / TASK_MIN_HEIGHT).toBe(TASK_ASPECT_RATIO);
  });

  it('defaults new tasks to the minimum size', () => {
    expect(defaultTaskSize()).toEqual({ width: TASK_MIN_WIDTH, height: TASK_MIN_HEIGHT });
  });

  it('never returns a height below the floor, however narrow the width', () => {
    expect(taskHeightForWidth(10)).toBe(TASK_MIN_HEIGHT);
    expect(taskHeightForWidth(TASK_MIN_WIDTH)).toBe(TASK_MIN_HEIGHT);
  });

  it('derives height from width above the floor', () => {
    expect(taskHeightForWidth(250)).toBe(100);
    expect(taskHeightForWidth(TASK_MAX_WIDTH)).toBe(TASK_MAX_WIDTH / TASK_ASPECT_RATIO);
  });
});

describe('sized task types', () => {
  it('covers bpmn:Task and its concrete subtypes', () => {
    expect(isSizedTaskType('bpmn:Task')).toBe(true);
    expect(isSizedTaskType('bpmn:UserTask')).toBe(true);
    expect(isSizedTaskType('bpmn:ServiceTask')).toBe(true);
  });

  it('excludes containers and non-tasks', () => {
    expect(isSizedTaskType('bpmn:SubProcess')).toBe(false);
    expect(isSizedTaskType('bpmn:CallActivity')).toBe(false);
    expect(isSizedTaskType('bpmn:StartEvent')).toBe(false);
    expect(isSizedTaskType(undefined)).toBe(false);
    expect(isSizedTaskType(null)).toBe(false);
  });

  it('lists every type exactly once', () => {
    expect(new Set(SIZED_TASK_TYPES).size).toBe(SIZED_TASK_TYPES.length);
  });
});

describe('width candidates', () => {
  it('walks from the minimum to the cap, smallest first', () => {
    const widths = taskWidthCandidates();
    expect(widths[0]).toBe(TASK_MIN_WIDTH);
    expect(widths.at(-1)).toBe(TASK_MAX_WIDTH);
    expect(widths[1] - widths[0]).toBe(TASK_GROWTH_STEP);
    expect([...widths].sort((a, b) => a - b)).toEqual(widths);
  });

  it('always includes the cap even when the step does not divide the range', () => {
    expect(taskWidthCandidates(100, 155, 25)).toEqual([100, 125, 150, 155]);
  });
});

describe('icon gutter', () => {
  it('reserves the gutter on every task that draws a type icon', () => {
    for (const type of ICON_BEARING_TASK_TYPES) {
      expect(taskIconGutter(type)).toBe(TASK_ICON_GUTTER);
    }
  });

  it('reserves nothing for a generic task, which draws no icon', () => {
    expect(taskIconGutter('bpmn:Task')).toBe(0);
  });

  it('excludes only the generic task from the icon-bearing set', () => {
    expect([...ICON_BEARING_TASK_TYPES].sort()).toEqual(
      SIZED_TASK_TYPES.filter((type) => type !== 'bpmn:Task').sort(),
    );
  });

  it('treats unknown and missing types as icon-less', () => {
    expect(taskIconGutter('bpmn:StartEvent')).toBe(0);
    expect(taskIconGutter(undefined)).toBe(0);
    expect(taskIconGutter(null)).toBe(0);
  });

  it('clears the widest glyph this package draws', () => {
    // Icons reach ~x=23 in Chromium client rects (see TASK_ICON_GUTTER).
    expect(TASK_ICON_GUTTER).toBeGreaterThan(23);
  });
});

describe('fitTaskSize', () => {
  it('returns the minimum size for an empty label', () => {
    expect(fitTaskSize(() => ({ width: 0, height: 0 }))).toEqual({
      width: TASK_MIN_WIDTH,
      height: TASK_MIN_HEIGHT,
    });
  });

  it('keeps the minimum size for a label that already fits', () => {
    expect(fitTaskSize(fakeMeasurer(60))).toEqual({
      width: TASK_MIN_WIDTH,
      height: TASK_MIN_HEIGHT,
    });
  });

  it('grows the box when the label does not fit vertically', () => {
    const size = fitTaskSize(fakeMeasurer(2000));
    expect(size.width).toBeGreaterThan(TASK_MIN_WIDTH);
    expect(size.height).toBeGreaterThan(TASK_MIN_HEIGHT);
  });

  it('holds the ratio while growing', () => {
    for (const textWidth of [400, 900, 2000, 5000]) {
      const size = fitTaskSize(fakeMeasurer(textWidth), { gutter: TASK_ICON_GUTTER });
      expect(size.height).toBe(taskHeightForWidth(size.width));
    }
  });

  it('grows monotonically with the amount of text', () => {
    const widths = [60, 300, 1200, 4000].map((text) => fitTaskSize(fakeMeasurer(text)).width);
    expect([...widths].sort((a, b) => a - b)).toEqual(widths);
  });

  it('leaves vertical padding rather than filling the box edge to edge', () => {
    const measure = fakeMeasurer(900);
    const { width, height } = fitTaskSize(measure);
    expect(measure(width).height).toBeLessThanOrEqual(height - 2 * TASK_LABEL_PADDING);
  });

  it('caps at the maximum width instead of growing without bound', () => {
    expect(fitTaskSize(() => ({ width: 0, height: Number.MAX_SAFE_INTEGER }))).toEqual({
      width: TASK_MAX_WIDTH,
      height: taskHeightForWidth(TASK_MAX_WIDTH),
    });
  });

  it('honours overridden bounds', () => {
    expect(fitTaskSize(() => ({ width: 0, height: 0 }), { minWidth: 200 })).toEqual({
      width: 200,
      height: 80,
    });
  });
});

describe('fitTaskSize — keeping a centred label clear of the icon', () => {
  it('leaves the gutter on both sides of the centred label', () => {
    const measure = fakeMeasurer(116);
    const { width } = fitTaskSize(measure, { gutter: TASK_ICON_GUTTER });
    const leadingEdge = (width - measure(width).width) / 2;
    expect(leadingEdge).toBeGreaterThanOrEqual(TASK_ICON_GUTTER);
  });

  it('widens a box whose label would otherwise run under the icon', () => {
    // 116px fits 150x60 vertically; only the icon gutter forces growth.
    const measure = fakeMeasurer(116);
    expect(fitTaskSize(measure).width).toBe(TASK_MIN_WIDTH);
    expect(fitTaskSize(measure, { gutter: TASK_ICON_GUTTER }).width).toBeGreaterThan(
      TASK_MIN_WIDTH,
    );
  });

  it('does not widen a generic task holding the same label', () => {
    const measure = fakeMeasurer(116);
    expect(fitTaskSize(measure, { gutter: taskIconGutter('bpmn:Task') }).width).toBe(
      TASK_MIN_WIDTH,
    );
  });

  it('grows an icon-bearing task at least as much as a generic one', () => {
    for (const textWidth of [60, 116, 300, 900, 2000]) {
      const generic = fitTaskSize(fakeMeasurer(textWidth), {
        gutter: taskIconGutter('bpmn:Task'),
      });
      const withIcon = fitTaskSize(fakeMeasurer(textWidth), {
        gutter: taskIconGutter('bpmn:UserTask'),
      });
      expect(withIcon.width).toBeGreaterThanOrEqual(generic.width);
    }
  });

  it('still returns the minimum size for a short label that already clears', () => {
    expect(fitTaskSize(fakeMeasurer(40), { gutter: TASK_ICON_GUTTER })).toEqual({
      width: TASK_MIN_WIDTH,
      height: TASK_MIN_HEIGHT,
    });
  });

  it('returns the smallest box satisfying both tests, not merely one that does', () => {
    const measure = fakeMeasurer(116);
    const { width } = fitTaskSize(measure, { gutter: TASK_ICON_GUTTER });
    const narrower = width - TASK_GROWTH_STEP;
    if (narrower >= TASK_MIN_WIDTH) {
      const failsVertically = measure(narrower).height > taskHeightForWidth(narrower) - 2 * TASK_LABEL_PADDING;
      const failsIconTest = measure(narrower).width + 2 * TASK_ICON_GUTTER > narrower;
      expect(failsVertically || failsIconTest).toBe(true);
    }
  });
});
