import { ReportFilter } from '../interfaces';

/**
 * Merge process-instance report filters with additional (caller- or context-supplied)
 * filters, deduping by field_name + operator so a field never appears twice.
 *
 * Tenant handling: any tenant_id already present in the report's filter_by is stripped,
 * because the global tenant context (passed via additionalFilters) is the single source
 * of truth. Additional filters override report filters on key collision, and a later
 * additional filter overrides an earlier one with the same key, so exactly one tenant_id
 * constraint survives even if additionalFilters itself contains more than one.
 */
export function mergeReportFilters(
  reportFilters: ReportFilter[],
  additionalFilters: ReportFilter[],
): ReportFilter[] {
  const filterKey = (f: ReportFilter) => `${f.field_name}::${f.operator ?? ''}`;

  // global context is the source of truth for tenant_id
  const merged: ReportFilter[] = (reportFilters || []).filter(
    (rf: ReportFilter) => rf.field_name !== 'tenant_id',
  );
  const indexByKey = new Map<string, number>(
    merged.map((f, i) => [filterKey(f), i]),
  );

  (additionalFilters || []).forEach((arf: ReportFilter) => {
    const key = filterKey(arf);
    const existing = indexByKey.get(key);
    if (existing !== undefined) {
      merged[existing] = arf; // additional filter wins → no duplicates
    } else {
      indexByKey.set(key, merged.length);
      merged.push(arf);
    }
  });

  return merged;
}
