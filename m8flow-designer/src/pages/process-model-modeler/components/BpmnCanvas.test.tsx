import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/** Minimal stand-in for diagram-js's CommandStack. */
class FakeCommandStack {
  _stackIdx = -1;
  canUndoValue = false;
  canRedoValue = false;
  undoCalls = 0;
  redoCalls = 0;
  canUndo() { return this.canUndoValue; }
  canRedo() { return this.canRedoValue; }
  undo() { this.undoCalls += 1; }
  redo() { this.redoCalls += 1; }
}

const stack = new FakeCommandStack();
const listeners = new Map<string, Array<(event: unknown) => void>>();

// bpmn-js itself needs a real canvas; only the seams BpmnCanvas touches are
// stubbed here (command stack, zoom, import, teardown).
vi.mock('m8flow-bpmn/lib/Modeler', () => ({
  default: class FakeModeler {
    get(name: string) {
      if (name === 'commandStack') return stack;
      if (name === 'canvas') return { zoom: () => {} };
      return undefined;
    }
    on(event: string, handler: (event: unknown) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), handler]);
    }
    off(event: string, handler: (event: unknown) => void) {
      listeners.set(event, (listeners.get(event) ?? []).filter((h) => h !== handler));
    }
    importXML() { return Promise.resolve({}); }
    destroy() {}
  },
}));
vi.mock('m8flow-bpmn/lib/features/connectorProfileCatalog', () => ({
  CONNECTOR_PROFILES_REQUESTED: 'spiff.connector_profiles.requested',
  CONNECTOR_PROFILES_RETURNED: 'spiff.connector_profiles.returned',
}));

import { BpmnCanvas } from './BpmnCanvas';

function fireCommandStackChanged() {
  act(() => {
    for (const handler of listeners.get('commandStack.changed') ?? []) handler({});
  });
}

describe('BpmnCanvas undo/redo', () => {
  beforeEach(() => {
    stack.canUndoValue = false;
    stack.canRedoValue = false;
    stack.undoCalls = 0;
    stack.redoCalls = 0;
    listeners.clear();
  });

  it('disables both controls until the command stack has history', async () => {
    render(<BpmnCanvas xml="<definitions />" />);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
  });

  it('enables and invokes undo/redo as the command stack reports them', async () => {
    render(<BpmnCanvas xml="<definitions />" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled());

    stack.canUndoValue = true;
    fireCommandStackChanged();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(stack.undoCalls).toBe(1);

    stack.canRedoValue = true;
    fireCommandStackChanged();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Redo' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
    expect(stack.redoCalls).toBe(1);
  });
});
