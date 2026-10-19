import { describe, expect, it, vi } from 'vitest';

// jsdom can't construct a real diagram-js canvas; capture the options the
// m8flow viewer hands to bpmn-js instead.
const received = vi.hoisted(() => [] as any[]);

vi.mock('bpmn-js/lib/NavigatedViewer', () => {
  function FakeBpmnViewer(options: any) {
    received.push(options);
  }
  FakeBpmnViewer.prototype._modules = [];
  FakeBpmnViewer.prototype.get = () => ({ getContainer: () => document.createElement('div') });
  return { default: FakeBpmnViewer };
});

const { default: NavigatedViewer } = await import('../lib/NavigatedViewer');

describe('NavigatedViewer m8flowRenderer options', () => {
  it('defaults neutralEndEvents on without dropping caller renderer flags', () => {
    new (NavigatedViewer as any)({ container: 'host', m8flowRenderer: { other: 1 } });
    new (NavigatedViewer as any)({ m8flowRenderer: { neutralEndEvents: false } });
    new (NavigatedViewer as any)();

    expect(received.map((options) => options.m8flowRenderer)).toEqual([
      { neutralEndEvents: true, other: 1 },
      { neutralEndEvents: false },
      { neutralEndEvents: true },
    ]);
    expect(received[0].container).toBe('host');
  });
});
