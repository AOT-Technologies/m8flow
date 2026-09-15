import { describe, expect, it } from 'vitest';

import { modelerCanvasKind } from './DiagramCanvas';

describe('modelerCanvasKind', () => {
  it('sends BPMN to the BPMN canvas and DMN to the DMN canvas', () => {
    expect(modelerCanvasKind('invoice.bpmn')).toBe('bpmn');
    expect(modelerCanvasKind('rules.DMN')).toBe('dmn');
  });

  it('sends JSON and markdown to the text canvas instead of BPMN import', () => {
    expect(modelerCanvasKind('form.json')).toBe('text');
    expect(modelerCanvasKind('README.md')).toBe('text');
  });

  it('sends form-schema companions to the form canvas, not generic JSON', () => {
    expect(modelerCanvasKind('sample-form-schema.json')).toBe('form');
    expect(modelerCanvasKind('sample-form-uischema.json')).toBe('form');
    expect(modelerCanvasKind('sample-form-exampledata.json')).toBe('form');
    expect(modelerCanvasKind('wfh-form.schema.json')).toBe('form');
    expect(modelerCanvasKind('test_payload.json')).toBe('text');
  });
});
