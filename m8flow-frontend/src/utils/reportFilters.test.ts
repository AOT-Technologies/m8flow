import { describe, it, expect } from 'vitest';
import { mergeReportFilters } from './reportFilters';

describe('mergeReportFilters', () => {
  it('collapses a caller tenant_id and a global tenant_id into one entry holding the global value', () => {
    const reportFilters = [
      { field_name: 'tenant_id', field_value: 'report-tenant', operator: 'equals' },
    ];
    const additionalFilters = [
      // caller-supplied tenant_id (e.g. via additionalReportFilters)
      { field_name: 'tenant_id', field_value: 'caller-tenant', operator: 'equals' },
      // global-context tenant_id, appended last → source of truth
      { field_name: 'tenant_id', field_value: 'global-tenant', operator: 'equals' },
    ];

    const result = mergeReportFilters(reportFilters, additionalFilters);

    const tenantFilters = result.filter((f) => f.field_name === 'tenant_id');
    expect(tenantFilters).toHaveLength(1);
    expect(tenantFilters[0].field_value).toBe('global-tenant');
  });

  it('always strips tenant_id present on the report side', () => {
    const reportFilters = [
      { field_name: 'tenant_id', field_value: 'report-tenant', operator: 'equals' },
      { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
    ];

    const result = mergeReportFilters(reportFilters, []);

    expect(result.some((f) => f.field_name === 'tenant_id')).toBe(false);
    expect(result).toHaveLength(1);
    expect(result[0].field_name).toBe('process_status');
  });

  it('preserves unrelated filters from both sources', () => {
    const reportFilters = [
      { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
    ];
    const additionalFilters = [
      { field_name: 'tenant_id', field_value: 'global-tenant', operator: 'equals' },
      { field_name: 'with_oldest_open_task', field_value: true },
    ];

    const result = mergeReportFilters(reportFilters, additionalFilters);

    expect(result).toHaveLength(3);
    expect(result.map((f) => f.field_name).sort()).toEqual([
      'process_status',
      'tenant_id',
      'with_oldest_open_task',
    ]);
  });

  it('keeps the same field_name with a different operator as separate entries', () => {
    const reportFilters = [
      { field_name: 'start', field_value: '2026-01-01', operator: 'greater_than' },
    ];
    const additionalFilters = [
      { field_name: 'start', field_value: '2026-12-31', operator: 'less_than' },
    ];

    const result = mergeReportFilters(reportFilters, additionalFilters);

    expect(result).toHaveLength(2);
  });

  it('overrides a report filter when an additional filter shares field_name + operator', () => {
    const reportFilters = [
      { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
    ];
    const additionalFilters = [
      { field_name: 'process_status', field_value: 'waiting', operator: 'equals' },
    ];

    const result = mergeReportFilters(reportFilters, additionalFilters);

    expect(result).toHaveLength(1);
    expect(result[0].field_value).toBe('waiting');
  });
});
