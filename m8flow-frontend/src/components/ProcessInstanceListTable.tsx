/**
 * Process-instance table — upstream + the m8flow status donut + the SA tenant column.
 *
 * Upstream invokes `filterComponent()` directly above the results, so wrapping
 * that one prop drops the donut between the filter bar and the table without
 * forking upstream or copying any of its body. Tables rendered without a filter
 * bar (process model tabs, extension-defined pages) get plain upstream
 * behaviour, which is also what keeps the donut off those pages.
 *
 * The Tenant column is a thin post-process over the report metadata for
 * super-admins on the all-instances table; row payloads already carry
 * `tenantName` from the backend report patch. The former fork also hid the "Go"
 * complete-task control for super-admins; completion remains backend-authorized.
 */
import { useEffect, useMemo, useState } from 'react';
import Upstream from '@spiff-core/components/ProcessInstanceListTable';
import { useTranslation } from 'react-i18next';
import type { ReportMetadata } from '../interfaces';
import UserService from '../services/UserService';
import ProcessInstanceStatusPieChart from './ProcessInstanceStatusPieChart';

type Filter = { field_name: string; field_value?: any; operator?: string };

const TENANT_COLUMN_ACCESSORS = new Set(['tenantName', 'tenant_name', 'tenantId']);

function withTenantColumn(
  reportMetadata: ReportMetadata | null | undefined,
  tenantHeader: string,
): ReportMetadata | null | undefined {
  if (!reportMetadata || reportMetadata.columns.length === 0) {
    return reportMetadata;
  }

  const alreadyPresent = reportMetadata.columns.some((column) =>
    TENANT_COLUMN_ACCESSORS.has(String(column.accessor)),
  );
  if (alreadyPresent) {
    return reportMetadata;
  }

  const firstColumn = reportMetadata.columns[0];
  const remainingColumns = reportMetadata.columns.slice(1);
  return {
    ...reportMetadata,
    columns: [
      ...(firstColumn ? [firstColumn] : []),
      { Header: tenantHeader, accessor: 'tenantName', filterable: false },
      ...remainingColumns,
    ],
  };
}

export default function ProcessInstanceListTable(props: Record<string, any>) {
  const { filterComponent, reportMetadata, variant } = props;
  const { t } = useTranslation();
  // Status picked by clicking a donut slice. Applied by rewriting the
  // reportMetadata handed to upstream, which re-queries whenever that object's
  // identity changes.
  const [chartStatus, setChartStatus] = useState('');

  // Last match wins, which is how upstream itself reads a status filter back into
  // its MultiSelect, so malformed metadata resolves the same way here, there, and
  // in the replacement below (which drops every status entry). field_value is
  // typed `any` upstream and does hold non-strings, hence the coercion.
  const statusFilters = ((reportMetadata?.filter_by || []) as Filter[]).filter(
    (f) => f.field_name === 'process_status',
  );
  const widgetStatusValue = statusFilters[statusFilters.length - 1]?.field_value;
  const widgetStatus = widgetStatusValue ? String(widgetStatusValue) : '';

  // The donut may own the status filter only when the page carries none of its own
  // AND upstream's metadata is settled. While `columns` is empty upstream adopts
  // the server's echo of whatever was posted, so injecting then would bake the
  // donut's filter into upstream's own state — where the MultiSelect still reads
  // empty and the user has no control that clears it.
  const chartMayOwnStatus =
    !widgetStatus && (reportMetadata?.columns?.length || 0) > 0;

  // Any upstream metadata change — a filter edit, Clear, a report load, a
  // For Me/All switch — retires the donut's selection. Keyed on the object rather
  // than on the status value alone: a selection made while the page's own status
  // filter was active would otherwise survive unseen and then take effect the
  // moment that filter was cleared.
  useEffect(() => {
    setChartStatus('');
  }, [reportMetadata, variant]);

  const showTenantColumn =
    UserService.isSuperAdmin() && (variant || 'for-me') === 'all';

  const metadataForUpstream = useMemo(() => {
    const withChartStatus =
      !reportMetadata || !chartStatus || !chartMayOwnStatus
        ? // Same object identity as the prop, so no extra fetch is provoked.
          reportMetadata
        : {
            ...reportMetadata,
            filter_by: [
              ...((reportMetadata.filter_by || []) as Filter[]).filter(
                (f) => f.field_name !== 'process_status',
              ),
              {
                field_name: 'process_status',
                field_value: chartStatus,
                operator: 'equals',
              },
            ],
          };

    // Memoized alongside the donut rewrite so the injected column does not hand
    // upstream a fresh object on every render.
    return showTenantColumn
      ? withTenantColumn(withChartStatus, t('tenant'))
      : withChartStatus;
  }, [reportMetadata, chartStatus, chartMayOwnStatus, showTenantColumn, t]);

  if (!filterComponent) {
    return <Upstream {...props} reportMetadata={metadataForUpstream} />;
  }

  const activeStatus = widgetStatus || chartStatus;

  // ponytail: a donut-driven status is not mirrored back into upstream's status
  // MultiSelect (upstream only reads it from report metadata on load). The donut
  // shows the selection instead. Give upstream a settable-filter seam if the two
  // need to stay visually in sync.

  // Variadic only to stay a faithful proxy. Upstream's sole call site is zero-arity,
  // but a decorator has no business narrowing the signature it wraps.
  const filterComponentWithChart = (...args: any[]) => (
    <>
      {filterComponent(...args)}
      <ProcessInstanceStatusPieChart
        variant={variant}
        reportMetadata={reportMetadata || null}
        selectedStatuses={activeStatus ? activeStatus.split(',') : []}
        onStatusClick={(status: string) => {
          if (!chartMayOwnStatus) {
            return;
          }
          setChartStatus((current) => (current === status ? '' : status));
        }}
      />
    </>
  );

  return (
    <Upstream
      {...props}
      filterComponent={filterComponentWithChart}
      reportMetadata={metadataForUpstream}
    />
  );
}

export { withTenantColumn };
