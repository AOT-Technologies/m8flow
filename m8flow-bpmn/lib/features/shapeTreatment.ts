/**
 * Pure geometry + color decisions behind the process modeler / process
 * instance viewer's custom BPMN icon set. `customRenderer.ts` owns the
 * SVG-DOM half (creating/removing real nodes); everything here is a plain
 * function of its arguments — no SVG, no DOM, no bpmn-js instance — so
 * "which color for which element type" and "what does this glyph look
 * like" are testable directly (see `test/shapeTreatment.test.ts`), without
 * the jsdom-lacks-SVG workaround the rest of this package's diagram
 * rendering is stuck with.
 *
 * `customRenderer.ts` calls these, gets back plain `ShapeSpec` descriptors,
 * and is the only place that turns a spec into a real SVG node
 * (`svgCreate`/`svgAppend`) or mutates one bpmn-js already drew.
 */

export type ShapeSpec = {
  tag: 'path' | 'circle';
  attrs: Record<string, string | number>;
};

// Operation-group color palette — see customRenderer.ts's own top-of-file
// comment for the full color-theory rationale (WCAG contrast, color-wheel
// spread, "don't rely on color alone since every group is also a distinct
// glyph shape").
export const SYSTEM_COLOR = 'var(--color-info)'; // every task/activity icon + system/communication events
export const FLOW_CONTROL_COLOR = 'var(--color-flow-control)'; // gateways + terminate/compensate/conditional/link
export const TIMER_COLOR = 'var(--color-warning)'; // Timer icon only
export const ERROR_COLOR = 'var(--color-destructive)'; // Error icon only

/**
 * bpmn-js's `bpmn:UserTask`/`bpmn:ServiceTask` handlers call `renderTask()`
 * first (box + embedded label + any markers), then append their own
 * type-icon shapes directly afterward — confirmed by reading
 * `BpmnRenderer.js`'s source for both handlers. That makes the icon shapes
 * always the *last* N children appended to the shape's gfx group, the
 * basis for `customRenderer.ts`'s tail-slice recolor.
 */
export const ICON_TAIL_COUNT: Record<string, number> = {
  'bpmn:UserTask': 3, // TASK_TYPE_USER_1/2/3 paths
  'bpmn:ServiceTask': 4, // 2 white cutout circles (left as-is) + 2 gear paths
  'bpmn:CallActivity': 1,
  'bpmn:AdHocSubProcess': 1,
};

/**
 * Per-type icon color for everything `ICON_TAIL_COUNT` recolors in place —
 * User Task, Service Task, and Call Activity are all "system" (blue); the
 * Ad-Hoc "~" marker stays "flow control" (violet), alongside the gateways
 * it shares an execution-order concern with.
 */
export const ICON_COLOR_BY_TYPE: Record<string, string> = {
  'bpmn:UserTask': SYSTEM_COLOR,
  'bpmn:ServiceTask': SYSTEM_COLOR,
  'bpmn:CallActivity': SYSTEM_COLOR,
  'bpmn:AdHocSubProcess': FLOW_CONTROL_COLOR,
};

/**
 * bpmn-js's own icon-path count per task subtype, read from each handler in
 * `BpmnRenderer.js` — the basis for how many trailing children
 * `buildCustomTaskSubtypeIconSpec`'s caller must strip before appending its
 * replacement glyph. ReceiveTask covers only the common (non-"instantiate")
 * case — this map's seed diagram never sets `instantiate`, so the 2-child
 * (start-circle + path) case isn't handled; flagged, not silently assumed
 * universal.
 */
export const CUSTOM_TASK_ICON_TAIL_COUNT: Record<string, number> = {
  'bpmn:ScriptTask': 1,
  'bpmn:ManualTask': 1,
  'bpmn:BusinessRuleTask': 2,
  'bpmn:SendTask': 1,
  'bpmn:ReceiveTask': 1,
};

export const CUSTOM_TASK_ICON_COLOR: Record<string, string> = {
  'bpmn:ScriptTask': SYSTEM_COLOR,
  'bpmn:ManualTask': SYSTEM_COLOR,
  'bpmn:BusinessRuleTask': SYSTEM_COLOR,
  'bpmn:SendTask': SYSTEM_COLOR,
  'bpmn:ReceiveTask': SYSTEM_COLOR,
};

/**
 * Per-event-definition-type color: Message/Signal/Escalation are "system &
 * communication" (blue); Error is its own dedicated "error handling" red;
 * Compensate/Conditional/Link/Terminate are all "flow control" (violet).
 * `bpmn:MultipleEventDefinition`/`ParallelMultipleEventDefinition` are
 * permanently out of scope — `bpmn-moddle`'s own schema doesn't define
 * them at all.
 */
export const EVENT_DEFINITION_COLOR: Record<string, string> = {
  'bpmn:MessageEventDefinition': SYSTEM_COLOR,
  'bpmn:SignalEventDefinition': SYSTEM_COLOR,
  'bpmn:EscalationEventDefinition': SYSTEM_COLOR,
  'bpmn:ErrorEventDefinition': ERROR_COLOR,
  'bpmn:CompensateEventDefinition': FLOW_CONTROL_COLOR,
  'bpmn:ConditionalEventDefinition': FLOW_CONTROL_COLOR,
  'bpmn:LinkEventDefinition': FLOW_CONTROL_COLOR,
  'bpmn:TerminateEventDefinition': FLOW_CONTROL_COLOR,
  // Timing — see `buildTimerIconSpecs`, reused directly rather than
  // duplicated: this map entry exists for documentation/lookup
  // completeness, not because anything reads it (the clock glyph hardcodes
  // `TIMER_COLOR` internally).
  'bpmn:TimerEventDefinition': TIMER_COLOR,
};

/**
 * Hand-drawn stroke-only glyphs for the 5 non-gateway/event task subtypes
 * bpmn-js draws its own icon for — same ~16x16 top-left icon area, replacing
 * bpmn-js's own glyph outright. Script reuses the folded-document motif
 * already established elsewhere in this codebase (`modelerBehaviors.ts`'s
 * own `SCRIPT_ICON_SVG`, used for the pre/post-script overlay badges).
 */
const CUSTOM_TASK_ICON_PATHS: Record<string, string> = {
  'bpmn:ScriptTask': 'M8,6 L18,6 L23,11 L23,24 L8,24 Z M18,6 L18,11 L23,11',
  'bpmn:ManualTask': 'M9,15 L19,15 L19,23 L9,23 Z M11,15 L11,10 M14,15 L14,9 M17,15 L17,10 M9,17 L6,19 L9,21',
  'bpmn:BusinessRuleTask': 'M7,8 L21,8 L21,22 L7,22 Z M7,13 L21,13 M7,18 L21,18 M14,8 L14,22',
  'bpmn:SendTask': 'M6,12 L22,5 L15,22 L12,14 Z M12,14 L22,5',
  'bpmn:ReceiveTask': 'M14,6 L14,17 M9,13 L14,18 L19,13 M6,21 L22,21',
};

export function buildCustomTaskSubtypeIconSpec(elementType: string): ShapeSpec | undefined {
  const d = CUSTOM_TASK_ICON_PATHS[elementType];
  if (!d) return undefined;
  return {
    tag: 'path',
    attrs: {
      d,
      fill: 'none',
      stroke: CUSTOM_TASK_ICON_COLOR[elementType] ?? SYSTEM_COLOR,
      strokeWidth: 1.6,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
    },
  };
}

/**
 * Custom gateway-marker icon (the user's "decision node" complaint) — two
 * crossing diagonals sized to ~32% of the gateway's own bounding box,
 * centered, replacing bpmn-js's own filled/mitered "X" outright.
 */
export function buildExclusiveGatewayMarkerSpec(width: number, height: number): ShapeSpec {
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.min(width, height) * 0.16;
  return {
    tag: 'path',
    attrs: {
      d: `M${cx - r},${cy - r} L${cx + r},${cy + r} M${cx + r},${cy - r} L${cx - r},${cy + r}`,
      fill: 'none',
      stroke: FLOW_CONTROL_COLOR,
      strokeWidth: 2.2,
      strokeLinecap: 'round',
    },
  };
}

export type GatewayMarkerKind = 'parallel' | 'inclusive' | 'eventBased' | 'complex';

/**
 * Markers for the remaining gateway types: Parallel gets a `+`, Inclusive
 * an `O` ring, Event-Based a plain ring (our seed diagram never sets
 * `eventGatewayType`, so stock bpmn-js draws only an unornamented inner
 * ring for it too, making a ring the faithful custom equivalent, not an
 * arbitrary simplification), Complex a 3-line asterisk.
 */
export function buildGatewayMarkerSpec(width: number, height: number, kind: GatewayMarkerKind): ShapeSpec {
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.min(width, height) * 0.16;
  const common = { fill: 'none', stroke: FLOW_CONTROL_COLOR, strokeWidth: 2.2, strokeLinecap: 'round' as const };

  if (kind === 'parallel') {
    return {
      tag: 'path',
      attrs: { d: `M${cx - r},${cy} L${cx + r},${cy} M${cx},${cy - r} L${cx},${cy + r}`, ...common },
    };
  }
  if (kind === 'inclusive' || kind === 'eventBased') {
    return { tag: 'circle', attrs: { cx, cy, r, fill: 'none', stroke: FLOW_CONTROL_COLOR, strokeWidth: 2.2 } };
  }
  const d = [0, 60, 120]
    .flatMap((deg) => {
      const rad = (deg * Math.PI) / 180;
      const dx = r * Math.cos(rad);
      const dy = r * Math.sin(rad);
      return [`M${cx - dx},${cy - dy}`, `L${cx + dx},${cy + dy}`];
    })
    .join(' ');
  return { tag: 'path', attrs: { d, ...common } };
}

/**
 * Timer face + hands. Sized to exactly match bpmn-js's own outer-ring
 * radius formula (`Math.round((width + height) / 4)`, read directly from
 * `drawCircle` in `BpmnRenderer.js`) — the same radius
 * `getShapePath`/`getCirclePath` use to crop connection waypoints to this
 * shape's edge, so the icon coincides with the attached sequence flow
 * regardless of how small the drawn icon is (found live: a smaller,
 * ~34%-sized circle left a visible gap, since diagram-js still crops to
 * the model's unchanged width/height). Filled `--color-card` (not `none`)
 * so the canvas's own dot-grid background doesn't show through.
 */
export function buildTimerIconSpecs(width: number, height: number): ShapeSpec[] {
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.round((width + height) / 4);
  return [
    { tag: 'circle', attrs: { cx, cy, r, fill: 'var(--color-card)', stroke: TIMER_COLOR, strokeWidth: 1.6 } },
    {
      tag: 'path',
      attrs: {
        d: `M${cx},${cy} L${cx},${cy - r * 0.65} M${cx},${cy} L${cx + r * 0.55},${cy}`,
        fill: 'none',
        stroke: TIMER_COLOR,
        strokeWidth: 1.6,
        strokeLinecap: 'round',
      },
    },
  ];
}

/**
 * Hand-drawn glyphs for the 8 non-Timer event-definition types (Timer is
 * `buildTimerIconSpecs` above), sized relative to the event's own ring
 * radius `r` so they scale consistently whatever the event's actual pixel
 * size. Returns `undefined` for an unrecognized/out-of-scope type
 * (Multiple) — callers only append when something's actually returned, so
 * an unhandled type intentionally leaves nothing drawn rather than
 * silently guessing.
 */
export function buildEventDefinitionIconSpec(
  width: number,
  height: number,
  defType: string | undefined,
): ShapeSpec | undefined {
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.round((width + height) / 4);
  const color = (defType && EVENT_DEFINITION_COLOR[defType]) ?? SYSTEM_COLOR;
  const common = {
    fill: 'none',
    stroke: color,
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };

  if (defType === 'bpmn:MessageEventDefinition') {
    const hw = r * 0.55;
    const hh = r * 0.4;
    return {
      tag: 'path',
      attrs: {
        d: `M${cx - hw},${cy - hh} L${cx + hw},${cy - hh} L${cx + hw},${cy + hh} L${cx - hw},${cy + hh} Z M${cx - hw},${cy - hh} L${cx},${cy + hh * 0.2} L${cx + hw},${cy - hh}`,
        ...common,
      },
    };
  }
  if (defType === 'bpmn:SignalEventDefinition') {
    const s = r * 0.6;
    return {
      tag: 'path',
      attrs: { d: `M${cx},${cy - s} L${cx + s * 0.87},${cy + s * 0.5} L${cx - s * 0.87},${cy + s * 0.5} Z`, ...common },
    };
  }
  if (defType === 'bpmn:ErrorEventDefinition') {
    return {
      tag: 'path',
      attrs: {
        d: `M${cx - r * 0.5},${cy - r * 0.65} L${cx + r * 0.2},${cy - r * 0.05} L${cx - r * 0.15},${cy + r * 0.1} L${cx + r * 0.5},${cy + r * 0.65}`,
        ...common,
      },
    };
  }
  if (defType === 'bpmn:EscalationEventDefinition') {
    return {
      tag: 'path',
      attrs: {
        d: `M${cx - r * 0.5},${cy + r * 0.35} L${cx},${cy - r * 0.5} L${cx + r * 0.5},${cy + r * 0.35} M${cx},${cy - r * 0.5} L${cx},${cy + r * 0.55}`,
        ...common,
      },
    };
  }
  if (defType === 'bpmn:CompensateEventDefinition') {
    return {
      tag: 'path',
      attrs: {
        d: `M${cx + r * 0.05},${cy - r * 0.55} L${cx - r * 0.5},${cy} L${cx + r * 0.05},${cy + r * 0.55} Z M${cx + r * 0.6},${cy - r * 0.55} L${cx + r * 0.05},${cy} L${cx + r * 0.6},${cy + r * 0.55} Z`,
        fill: color,
        stroke: color,
        strokeWidth: 1,
        strokeLinejoin: 'round',
      },
    };
  }
  if (defType === 'bpmn:ConditionalEventDefinition') {
    return {
      tag: 'path',
      attrs: {
        d: `M${cx - r * 0.55},${cy - r * 0.4} L${cx + r * 0.55},${cy - r * 0.4} M${cx - r * 0.55},${cy} L${cx + r * 0.55},${cy} M${cx - r * 0.55},${cy + r * 0.4} L${cx + r * 0.55},${cy + r * 0.4}`,
        ...common,
      },
    };
  }
  if (defType === 'bpmn:LinkEventDefinition') {
    return {
      tag: 'path',
      attrs: {
        d: `M${cx - r * 0.55},${cy} L${cx + r * 0.3},${cy} M${cx},${cy - r * 0.4} L${cx + r * 0.55},${cy} L${cx},${cy + r * 0.4}`,
        ...common,
      },
    };
  }
  if (defType === 'bpmn:TerminateEventDefinition') {
    return { tag: 'circle', attrs: { cx, cy, r: r * 0.45, fill: color, stroke: 'none' } };
  }
  return undefined;
}

/**
 * Unified event badge — every typed event (Start/End/Intermediate/Boundary)
 * of any event-definition type draws through this one ring+glyph
 * construction (live user feedback: "events dont have a common style.
 * Schedule is different to the rest of the events. Schedule looks
 * better."). Timer is special-cased first since `buildTimerIconSpecs`
 * draws its own ring — calling the shared generic ring first too would
 * double it up; every other type gets one shared ring plus
 * `buildEventDefinitionIconSpec`'s glyph, so ring and icon always share one
 * hue. Callers strip every existing child before appending these specs —
 * same "replace outright" pattern as every custom icon here.
 */
export function buildUnifiedEventIconSpecs(width: number, height: number, defType: string): ShapeSpec[] {
  if (defType === 'bpmn:TimerEventDefinition') {
    return buildTimerIconSpecs(width, height);
  }

  const cx = width / 2;
  const cy = height / 2;
  const r = Math.round((width + height) / 4);
  const color = EVENT_DEFINITION_COLOR[defType] ?? SYSTEM_COLOR;

  const specs: ShapeSpec[] = [
    { tag: 'circle', attrs: { cx, cy, r, fill: 'var(--color-card)', stroke: color, strokeWidth: 1.6 } },
  ];
  const glyph = buildEventDefinitionIconSpec(width, height, defType);
  if (glyph) specs.push(glyph);
  return specs;
}

/**
 * `element.businessObject.eventDefinitions[0].$type` — the one detail
 * every typed-event branch in `customRenderer.ts` needs before it can pick
 * a treatment. Pure: takes the diagram-js model object, no DOM.
 */
export function getEventDefinitionType(element: {
  businessObject?: { eventDefinitions?: { $type?: string }[] };
}): string | undefined {
  const eventDefinitions = element.businessObject?.eventDefinitions ?? [];
  return eventDefinitions[0]?.$type;
}
