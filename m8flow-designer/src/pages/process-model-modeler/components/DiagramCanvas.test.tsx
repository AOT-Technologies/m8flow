import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { DiagramCanvas, modelerCanvasKind } from './DiagramCanvas';

describe('modelerCanvasKind', () => {
  it.each(['form-schema.json', 'notes.md'])('renders %s without an editor for read-only users', (fileName) => {
    render(<DiagramCanvas fileName={fileName} xml="readable content" readOnly />);
    expect(screen.getByLabelText('Read-only file content')).toHaveTextContent('readable content');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });
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
