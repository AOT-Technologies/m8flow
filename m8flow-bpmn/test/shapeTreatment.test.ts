import { describe, expect, it } from 'vitest';
import {
  buildCustomTaskSubtypeIconSpec,
  buildEventDefinitionIconSpec,
  buildExclusiveGatewayMarkerSpec,
  buildGatewayMarkerSpec,
  buildTimerIconSpecs,
  buildUnifiedEventIconSpecs,
  CUSTOM_TASK_ICON_TAIL_COUNT,
  ERROR_COLOR,
  EVENT_DEFINITION_COLOR,
  FLOW_CONTROL_COLOR,
  getEventDefinitionType,
  ICON_COLOR_BY_TYPE,
  ICON_TAIL_COUNT,
  SYSTEM_COLOR,
  TIMER_COLOR,
} from '../lib/features/shapeTreatment';

describe('lookup tables', () => {
  it('colors every task-type icon system-blue except the ad-hoc marker', () => {
    expect(ICON_COLOR_BY_TYPE['bpmn:UserTask']).toBe(SYSTEM_COLOR);
    expect(ICON_COLOR_BY_TYPE['bpmn:ServiceTask']).toBe(SYSTEM_COLOR);
    expect(ICON_COLOR_BY_TYPE['bpmn:CallActivity']).toBe(SYSTEM_COLOR);
    expect(ICON_COLOR_BY_TYPE['bpmn:AdHocSubProcess']).toBe(FLOW_CONTROL_COLOR);
  });

  it('keeps ICON_TAIL_COUNT and ICON_COLOR_BY_TYPE in sync', () => {
    expect(Object.keys(ICON_TAIL_COUNT).sort()).toEqual(Object.keys(ICON_COLOR_BY_TYPE).sort());
  });

  it('keeps CUSTOM_TASK_ICON_TAIL_COUNT entries all system-colored', () => {
    for (const type of Object.keys(CUSTOM_TASK_ICON_TAIL_COUNT)) {
      expect(buildCustomTaskSubtypeIconSpec(type)?.attrs.stroke).toBe(SYSTEM_COLOR);
    }
  });

  it('sorts event-definition colors into their operation groups', () => {
    expect(EVENT_DEFINITION_COLOR['bpmn:MessageEventDefinition']).toBe(SYSTEM_COLOR);
    expect(EVENT_DEFINITION_COLOR['bpmn:ErrorEventDefinition']).toBe(ERROR_COLOR);
    expect(EVENT_DEFINITION_COLOR['bpmn:TerminateEventDefinition']).toBe(FLOW_CONTROL_COLOR);
    expect(EVENT_DEFINITION_COLOR['bpmn:TimerEventDefinition']).toBe(TIMER_COLOR);
  });
});

describe('buildCustomTaskSubtypeIconSpec', () => {
  it('returns a stroke-only path for a known task subtype', () => {
    const spec = buildCustomTaskSubtypeIconSpec('bpmn:ScriptTask');
    expect(spec).toMatchObject({ tag: 'path', attrs: { fill: 'none', stroke: SYSTEM_COLOR } });
    expect(spec?.attrs.d).toMatch(/^M8,6/);
  });

  it('returns undefined for a type with no custom glyph', () => {
    expect(buildCustomTaskSubtypeIconSpec('bpmn:Task')).toBeUndefined();
  });
});

describe('buildExclusiveGatewayMarkerSpec', () => {
  it('centers the X on the gateway bounding box', () => {
    const spec = buildExclusiveGatewayMarkerSpec(40, 40);
    expect(spec.tag).toBe('path');
    expect(spec.attrs.stroke).toBe(FLOW_CONTROL_COLOR);
    // cx = cy = 20, r = 40 * 0.16 = 6.4
    expect(spec.attrs.d).toBe('M13.6,13.6 L26.4,26.4 M26.4,13.6 L13.6,26.4');
  });
});

describe('buildGatewayMarkerSpec', () => {
  it('draws a plus for parallel', () => {
    const spec = buildGatewayMarkerSpec(40, 40, 'parallel');
    expect(spec.tag).toBe('path');
    expect(spec.attrs.d).toBe('M13.6,20 L26.4,20 M20,13.6 L20,26.4');
  });

  it('draws a ring for inclusive and event-based', () => {
    expect(buildGatewayMarkerSpec(40, 40, 'inclusive')).toMatchObject({ tag: 'circle', attrs: { r: 6.4 } });
    expect(buildGatewayMarkerSpec(40, 40, 'eventBased')).toMatchObject({ tag: 'circle', attrs: { r: 6.4 } });
  });

  it('draws a 3-line asterisk for complex', () => {
    const spec = buildGatewayMarkerSpec(40, 40, 'complex');
    expect(spec.tag).toBe('path');
    // 3 segments -> 3 "M...L..." pairs joined by a space
    expect(spec.attrs.d).toMatch(/^(M[\d.-]+,[\d.-]+ L[\d.-]+,[\d.-]+ ?){3}$/);
  });
});

describe('buildTimerIconSpecs', () => {
  it('returns a face circle and a hands path sized off the outer-ring radius', () => {
    const [face, hands] = buildTimerIconSpecs(36, 36);
    expect(face).toMatchObject({ tag: 'circle', attrs: { cx: 18, cy: 18, r: 18, stroke: TIMER_COLOR } });
    expect(hands.tag).toBe('path');
    expect(hands.attrs.stroke).toBe(TIMER_COLOR);
  });
});

describe('buildEventDefinitionIconSpec', () => {
  it('draws each known definition type in its operation-group color', () => {
    expect(buildEventDefinitionIconSpec(36, 36, 'bpmn:MessageEventDefinition')?.attrs.stroke).toBe(SYSTEM_COLOR);
    expect(buildEventDefinitionIconSpec(36, 36, 'bpmn:ErrorEventDefinition')?.attrs.stroke).toBe(ERROR_COLOR);
    expect(buildEventDefinitionIconSpec(36, 36, 'bpmn:LinkEventDefinition')?.attrs.stroke).toBe(FLOW_CONTROL_COLOR);
  });

  it('fills rather than strokes Compensate and Terminate', () => {
    const compensate = buildEventDefinitionIconSpec(36, 36, 'bpmn:CompensateEventDefinition');
    expect(compensate?.attrs.fill).toBe(FLOW_CONTROL_COLOR);

    const terminate = buildEventDefinitionIconSpec(36, 36, 'bpmn:TerminateEventDefinition');
    expect(terminate).toMatchObject({ tag: 'circle', attrs: { fill: FLOW_CONTROL_COLOR, stroke: 'none' } });
  });

  it('returns undefined for an out-of-scope definition type', () => {
    expect(buildEventDefinitionIconSpec(36, 36, 'bpmn:MultipleEventDefinition')).toBeUndefined();
    expect(buildEventDefinitionIconSpec(36, 36, undefined)).toBeUndefined();
  });
});

describe('buildUnifiedEventIconSpecs', () => {
  it('delegates to the timer face+hands construction for Timer', () => {
    const specs = buildUnifiedEventIconSpecs(36, 36, 'bpmn:TimerEventDefinition');
    expect(specs).toHaveLength(2);
    expect(specs[0].attrs.stroke).toBe(TIMER_COLOR);
  });

  it('draws one shared ring plus the type glyph for every other definition', () => {
    const specs = buildUnifiedEventIconSpecs(36, 36, 'bpmn:ErrorEventDefinition');
    expect(specs).toHaveLength(2);
    expect(specs[0]).toMatchObject({ tag: 'circle', attrs: { stroke: ERROR_COLOR, fill: 'var(--color-card)' } });
    expect(specs[1].attrs.stroke).toBe(ERROR_COLOR);
  });
});

describe('getEventDefinitionType', () => {
  it('reads the first event definition off the business object', () => {
    const element = { businessObject: { eventDefinitions: [{ $type: 'bpmn:TimerEventDefinition' }] } };
    expect(getEventDefinitionType(element)).toBe('bpmn:TimerEventDefinition');
  });

  it('returns undefined when there are no event definitions', () => {
    expect(getEventDefinitionType({ businessObject: {} })).toBeUndefined();
    expect(getEventDefinitionType({})).toBeUndefined();
  });
});
