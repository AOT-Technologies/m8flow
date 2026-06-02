import { describe, it, expect } from 'vitest';
import { processGroupToLite } from './ProcessModelTreePage';

/**
 * Regression test for the tenant chip bug: processGroupToLite used to drop the
 * tenantId/tenantName fields the API attaches to each process group, so the
 * list/tree view never rendered the tenant chip even though the data was present.
 */
describe('processGroupToLite', () => {
  it('preserves tenantId and tenantName from the API response', () => {
    const lite = processGroupToLite({
      id: 'helloworld',
      display_name: 'helloworld',
      description: 'hello',
      process_models: [],
      process_groups: [],
      tenantId: 'tenant-1',
      tenantName: 'sam',
    } as any);

    expect(lite.tenantName).toBe('sam');
    expect(lite.tenantId).toBe('tenant-1');
  });

  it('preserves tenant fields on nested process groups', () => {
    const lite = processGroupToLite({
      id: 'root',
      display_name: 'root',
      description: '',
      process_models: [],
      process_groups: [
        {
          id: 'abil',
          display_name: 'abil',
          description: '',
          process_models: [],
          process_groups: [],
          tenantId: 'tenant-2',
          tenantName: 'm8flow',
        },
      ],
      tenantId: 'tenant-1',
      tenantName: 'sam',
    } as any);

    expect(lite.tenantName).toBe('sam');
    expect(lite.process_groups?.[0].tenantName).toBe('m8flow');
    expect(lite.process_groups?.[0].tenantId).toBe('tenant-2');
  });

  it('leaves tenant fields undefined when the API omits them', () => {
    const lite = processGroupToLite({
      id: 'no-tenant',
      display_name: 'no-tenant',
      description: '',
      process_models: [],
      process_groups: [],
    } as any);

    expect(lite.tenantName).toBeUndefined();
    expect(lite.tenantId).toBeUndefined();
  });
});
