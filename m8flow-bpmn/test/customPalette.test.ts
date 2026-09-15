import { describe, expect, it, vi } from 'vitest';

import {
  CustomPaletteProvider,
  DROPPED_PALETTE_ACTIONS,
  KEEP_SCOPE_PALETTE_ACTIONS,
  customPaletteModule,
} from '../lib/features/customPalette';

function mountPalette() {
  let provider: { getPaletteEntries: () => Record<string, unknown> } | undefined;
  const palette = {
    registerProvider(instance: { getPaletteEntries: () => Record<string, unknown> }) {
      provider = instance;
    },
  };
  const create = { start: vi.fn() };
  const elementFactory = {
    createShape: vi.fn((attrs: Record<string, unknown>) => ({ ...attrs })),
    createParticipantShape: vi.fn(() => ({ type: 'bpmn:Participant' })),
  };
  const spaceTool = { activateSelection: vi.fn() };
  const lassoTool = { activateSelection: vi.fn() };
  const handTool = { activateHand: vi.fn() };
  const globalConnect = { start: vi.fn() };
  const translate = (s: string) => s;
  new (CustomPaletteProvider as unknown as new (...args: unknown[]) => void)(
    palette,
    create,
    elementFactory,
    spaceTool,
    lassoTool,
    handTool,
    globalConnect,
    translate,
  );
  if (!provider) {
    throw new Error('CustomPaletteProvider did not register');
  }
  return { provider, create, elementFactory, spaceTool, lassoTool, handTool, globalConnect };
}

describe('customPaletteModule', () => {
  it('overrides the stock paletteProvider DI key', () => {
    expect(customPaletteModule.__init__).toEqual(['paletteProvider']);
    expect(customPaletteModule.paletteProvider[0]).toBe('type');
  });

  it('offers the old bpmn-js set minus data store', () => {
    const { provider } = mountPalette();
    const actions = Object.keys(provider.getPaletteEntries()).filter((id) => id !== 'tool-separator');
    expect(actions).toEqual([...KEEP_SCOPE_PALETTE_ACTIONS]);
    for (const dropped of DROPPED_PALETTE_ACTIONS) {
      expect(actions).not.toContain(dropped);
    }
  });

  it('activates the space tool from the palette', () => {
    const { provider, spaceTool } = mountPalette();
    const entries = provider.getPaletteEntries() as Record<
      string,
      { action?: { click?: (event: unknown) => void } }
    >;
    entries['space-tool'].action?.click?.({});
    expect(spaceTool.activateSelection).toHaveBeenCalledTimes(1);
  });

  it('creates an ordinary expanded subprocess with a start event, not an event subprocess', () => {
    const { provider, create, elementFactory } = mountPalette();
    const entries = provider.getPaletteEntries() as Record<
      string,
      { action?: { click?: (event: unknown) => void } }
    >;
    entries['create.subprocess-expanded'].action?.click?.('click-event');

    expect(elementFactory.createShape).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'bpmn:SubProcess', isExpanded: true }),
    );
    expect(elementFactory.createShape).not.toHaveBeenCalledWith(
      expect.objectContaining({ triggeredByEvent: true }),
    );
    expect(create.start).toHaveBeenCalledWith(
      'click-event',
      expect.arrayContaining([
        expect.objectContaining({ type: 'bpmn:SubProcess', isExpanded: true }),
        expect.objectContaining({ type: 'bpmn:StartEvent' }),
      ]),
      expect.objectContaining({ hints: expect.any(Object) }),
    );
  });

  it('creates a pool/participant via createParticipantShape', () => {
    const { provider, create, elementFactory } = mountPalette();
    const entries = provider.getPaletteEntries() as Record<
      string,
      { action?: { click?: (event: unknown) => void } }
    >;
    entries['create.participant-expanded'].action?.click?.('click-event');
    expect(elementFactory.createParticipantShape).toHaveBeenCalledTimes(1);
    expect(create.start).toHaveBeenCalledWith('click-event', { type: 'bpmn:Participant' });
  });
});
