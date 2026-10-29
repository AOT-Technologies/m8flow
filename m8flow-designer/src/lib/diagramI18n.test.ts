import { describe, expect, it, vi } from 'vitest';

import i18n, { DIAGRAM_NS } from '@/i18n';

import { followDiagramLanguage, translateDiagram } from './diagramI18n';

describe('translateDiagram', () => {
  it('returns the English template when the language has no entry', () => {
    expect(translateDiagram('Not a catalogued string')).toBe('Not a catalogued string');
  });

  it('looks up the current language, keeping dots in keys literal', async () => {
    await i18n.loadNamespaces(DIAGRAM_NS);
    await i18n.changeLanguage('de');
    expect(translateDiagram('Zoom in')).toBe('Vergrößern');
    expect(translateDiagram('Data stores are not supported in this host.')).toBe(
      'Datenspeicher werden in diesem Host nicht unterstützt.',
    );
  });

  it('substitutes {name} replacements like diagram-js and keeps unknown ones', () => {
    expect(translateDiagram('Append {type} to {target}', { type: 'Task' })).toBe('Append Task to {target}');
  });
});

describe('followDiagramLanguage', () => {
  it('refreshes on a language switch until unsubscribed and coalesces calls', async () => {
    const refresh = vi.fn();
    const stop = followDiagramLanguage(refresh);

    await i18n.changeLanguage('de');
    expect(refresh).toHaveBeenCalledTimes(1);

    refresh.mockClear();
    stop();
    await i18n.changeLanguage('es');
    expect(refresh).not.toHaveBeenCalled();
  });

  it('ignores loaded events for unrelated namespaces', async () => {
    const refresh = vi.fn();
    const stop = followDiagramLanguage(refresh);
    await new Promise((resolve) => setTimeout(resolve, 20));
    refresh.mockClear();

    // Emitting loaded for an unrelated namespace like 'pages' or 'translation'
    (i18n as any).emit('loaded', { [i18n.language]: { pages: true } });
    (i18n as any).emit('loaded', {});

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(refresh).not.toHaveBeenCalled();

    // Emitting loaded for DIAGRAM_NS on the active language triggers refresh
    (i18n as any).emit('loaded', { [i18n.language]: { [DIAGRAM_NS]: true } });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(refresh).toHaveBeenCalledTimes(1);

    stop();
  });
});
