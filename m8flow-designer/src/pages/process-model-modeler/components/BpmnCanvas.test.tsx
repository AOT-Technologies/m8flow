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
  execute() { throw new Error('read-only command should not execute'); }
}

const stack = new FakeCommandStack();
const listeners = new Map<string, Array<(event: unknown) => void>>();
const constructed: Array<Record<string, unknown>> = [];
const fakeEventBus = { fire: vi.fn() };
let zoomControlsService: { refit: () => void } | undefined = { refit: () => {} };

// bpmn-js itself needs a real canvas; only the seams BpmnCanvas touches are
// stubbed here (command stack, zoom, event bus, import, teardown).
vi.mock('m8flow-bpmn/lib/Modeler', () => ({
  default: class FakeModeler {
    constructor(options: Record<string, unknown>) {
      constructed.push(options);
    }
    get(name: string) {
      if (name === 'commandStack') return stack;
      if (name === 'canvas') return { zoom: () => {} };
      if (name === 'm8flowZoomControls') return zoomControlsService;
      if (name === 'eventBus') return fakeEventBus;
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

import i18n from '@/i18n';
import { diagramTranslateModule } from '@/lib/diagramI18n';

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

describe('BpmnCanvas toolbar', () => {
  it('mounts the zoom controls in the top toolbar, beside undo/redo', async () => {
    render(<BpmnCanvas xml="<definitions />" />);
    await waitFor(() => expect(constructed[constructed.length - 1]?.zoomControls).toBeDefined());

    const slot = (constructed[constructed.length - 1].zoomControls as { parent: HTMLElement }).parent;
    expect(slot).toBeInstanceOf(HTMLElement);
    expect(slot.parentElement).toContainElement(screen.getByRole('button', { name: 'Undo' }));
  });
});

describe('BpmnCanvas properties panel', () => {
  beforeEach(() => {
    listeners.clear();
  });

  it('reopens a hidden panel when a context pad entry asks to show a panel field', async () => {
    render(<BpmnCanvas xml="<definitions />" />);
    fireEvent.click(await screen.findByTitle('Hide properties panel'));
    expect(screen.getByTitle('Show properties panel')).toBeInTheDocument();

    act(() => {
      for (const handler of listeners.get('propertiesPanel.showEntry') ?? []) {
        handler({ id: 'pythonScript_spiffworkflow:PreScript' });
      }
    });

    expect(screen.getByTitle('Hide properties panel')).toBeInTheDocument();
  });

  it('hides the panel in expanded view until the user opens it, and restores it on exit', async () => {
    render(<BpmnCanvas xml="<definitions />" />);
    await screen.findByTitle('Hide properties panel');
    const fire = (event: string, payload: unknown) =>
      act(() => {
        for (const handler of listeners.get(event) ?? []) handler(payload);
      });

    fire('m8flow.expand.changed', { expanded: true });
    expect(screen.getByTitle('Show properties panel')).toBeInTheDocument();

    // Clicking diagram elements does not bring it back; the toggle does.
    fire('element.click', { element: { id: 'Task_1' } });
    expect(screen.getByTitle('Show properties panel')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Show properties panel'));
    expect(screen.getByTitle('Hide properties panel')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Hide properties panel'));

    fire('m8flow.expand.changed', { expanded: false });
    expect(screen.getByTitle('Hide properties panel')).toBeInTheDocument();

    // A panel hidden before expanding stays hidden after leaving.
    fireEvent.click(screen.getByTitle('Hide properties panel'));
    fire('m8flow.expand.changed', { expanded: true });
    fire('m8flow.expand.changed', { expanded: false });
    expect(screen.getByTitle('Show properties panel')).toBeInTheDocument();
  });

  it('refits through the zoom controls on the next frame, after the panel has changed', async () => {
    // Let frames earlier tests queued run first, so they can't reach this
    // test's refit spy.
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const frames: FrameRequestCallback[] = [];
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const panelAtRefit: string[] = [];
    zoomControlsService = {
      refit: vi.fn(() => {
        panelAtRefit.push(screen.queryByTitle('Show properties panel') ? 'hidden' : 'shown');
      }),
    };
    try {
      render(<BpmnCanvas xml="<definitions />" />);
      await screen.findByTitle('Hide properties panel');
      const fire = (expanded: boolean) =>
        act(() => {
          for (const handler of listeners.get('m8flow.expand.changed') ?? []) handler({ expanded });
        });
      const runFrames = () => act(() => frames.splice(0).forEach((callback) => callback(0)));

      fire(true);
      expect(zoomControlsService.refit).not.toHaveBeenCalled();
      runFrames();
      fire(false);
      runFrames();
      // Each refit saw the panel already hidden / restored for its mode.
      expect(panelAtRefit).toEqual(['hidden', 'shown']);
    } finally {
      zoomControlsService = { refit: () => {} };
      raf.mockRestore();
    }
  });

  it('survives expand / collapse when the modeler has no zoom controls service', async () => {
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    zoomControlsService = undefined;
    try {
      render(<BpmnCanvas xml="<definitions />" />);
      await screen.findByTitle('Hide properties panel');
      const fire = (expanded: boolean) =>
        act(() => {
          for (const handler of listeners.get('m8flow.expand.changed') ?? []) handler({ expanded });
        });

      expect(() => fire(true)).not.toThrow();
      expect(screen.getByTitle('Show properties panel')).toBeInTheDocument();
      expect(() => fire(false)).not.toThrow();
      expect(screen.getByTitle('Hide properties panel')).toBeInTheDocument();
    } finally {
      zoomControlsService = { refit: () => {} };
      raf.mockRestore();
    }
  });

  it('keeps the properties panel visible while making the modeler read-only', async () => {
    render(<BpmnCanvas xml="<definitions />" readOnly />);

    await waitFor(() => expect(screen.getByTitle('Hide properties panel')).toBeInTheDocument());
    expect(screen.queryByTitle('Undo')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Redo')).not.toBeInTheDocument();

    // Some diagram-js builds append the context pad outside the canvas host.
    // It must still be hidden when created after the read-only effect.
    const contextPad = document.createElement('div');
    contextPad.className = 'djs-context-pad open';
    document.body.append(contextPad);

    await waitFor(() => expect(contextPad.style.display).toBe('none'));
    expect(contextPad.style.getPropertyPriority('display')).toBe('important');
    contextPad.remove();
  });
});

describe('BpmnCanvas decision table', () => {
  const files = [
    { name: 'decide.bpmn' },
    { name: 'check-approval-route.dmn', decision_id: 'Decision_check_approval_route' },
  ];

  beforeEach(() => {
    listeners.clear();
  });

  function emit(event: string, payload: Record<string, unknown>) {
    act(() => {
      for (const handler of listeners.get(event) ?? []) handler(payload);
    });
  }

  it('offers the decision id, which calledDecisionId must hold, not the file name', async () => {
    render(<BpmnCanvas xml="<definitions />" files={files} />);
    await waitFor(() => expect(listeners.get('spiff.dmn_files.requested')).toBeDefined());
    const eventBus = { fire: vi.fn() };

    emit('spiff.dmn_files.requested', { eventBus });

    expect(eventBus.fire).toHaveBeenCalledWith('spiff.dmn_files.returned', {
      options: [{ label: 'check-approval-route.dmn', value: 'Decision_check_approval_route' }],
    });
  });

  it('launches the editor on the file holding the selected decision', async () => {
    const onLaunchDmnEditor = vi.fn();
    render(<BpmnCanvas xml="<definitions />" files={files} onLaunchDmnEditor={onLaunchDmnEditor} />);
    await waitFor(() => expect(listeners.get('spiff.dmn.edit')).toBeDefined());

    emit('spiff.dmn.edit', { value: 'Decision_check_approval_route' });

    expect(onLaunchDmnEditor).toHaveBeenCalledWith('check-approval-route.dmn');
  });
});

describe('BpmnCanvas language', () => {
  it('installs the designer translate service and re-renders the diagram on a language switch', async () => {
    render(<BpmnCanvas xml="<definitions />" />);
    await waitFor(() => expect(constructed[constructed.length - 1]?.additionalModules).toContain(diagramTranslateModule));

    fakeEventBus.fire.mockClear();
    await act(() => i18n.changeLanguage('de'));

    expect(fakeEventBus.fire).toHaveBeenCalledWith('i18n.changed');
  });
});
