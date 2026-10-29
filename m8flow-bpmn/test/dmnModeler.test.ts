import { describe, expect, it, vi } from 'vitest';

// jsdom can't construct real dmn-js views; capture the options the m8flow
// wrapper hands to dmn-js instead.
const received = vi.hoisted(() => [] as any[]);

vi.mock('dmn-js/lib/Modeler', () => ({
  default: class FakeDmnModeler {
    constructor(options: any) {
      received.push(options);
    }
  },
}));

const { default: DmnModeler } = await import('../lib/DmnModeler');
const { decisionTableI18nModule, expressionViewI18nModule } = await import('../lib/features/dmnViewI18n');
const { canvasI18nModule } = await import('../lib/features/canvasI18n');
const { propertiesPanelI18nModule } = await import('../lib/features/propertiesPanelI18n');

describe('DmnModeler view options', () => {
  it('adds the i18n modules to every view and lets host modules override them', () => {
    received.length = 0;
    const host = { translate: ['value', (template: string) => template] };

    new (DmnModeler as any)({
      container: 'host',
      propertiesPanel: { parent: 'panel' },
      drd: { additionalModules: [host] },
      decisionTable: { additionalModules: [host], keyboard: { bindTo: 'doc' } },
      literalExpression: { additionalModules: [host] },
    });
    const [options] = received;

    // Host modules last: a host `translate` override wins in DI.
    expect(options.decisionTable).toEqual({ keyboard: { bindTo: 'doc' }, additionalModules: [decisionTableI18nModule, host] });
    expect(options.literalExpression.additionalModules).toEqual([expressionViewI18nModule, host]);
    // A view the host did not configure still gets its module.
    expect(options.boxedExpression.additionalModules).toEqual([expressionViewI18nModule]);
    expect(options.drd.additionalModules).toEqual(expect.arrayContaining([propertiesPanelI18nModule, canvasI18nModule]));
    expect(options.drd.additionalModules[options.drd.additionalModules.length - 1]).toBe(host);
    expect(options.drd.propertiesPanel).toEqual({ parent: 'panel' });
    expect(options.container).toBe('host');
  });
});
