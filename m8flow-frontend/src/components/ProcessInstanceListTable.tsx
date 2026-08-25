import type { ComponentProps } from 'react';
import UpstreamProcessInstanceListTable from '@spiff-core/components/ProcessInstanceListTable';
import { useTranslation } from 'react-i18next';
import type { ReportMetadata } from '../interfaces';
import UserService from '../services/UserService';

type ProcessInstanceListTableProps = ComponentProps<
  typeof UpstreamProcessInstanceListTable
>;

const TENANT_COLUMN_ACCESSORS = new Set(['tenantName', 'tenant_name', 'tenantId']);

function withTenantColumn(
  reportMetadata: ReportMetadata | null | undefined,
  tenantHeader: string,
): ReportMetadata | null | undefined {
  if (!reportMetadata) {
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

export default function ProcessInstanceListTable(
  props: ProcessInstanceListTableProps,
) {
  const { t } = useTranslation();
  const showTenantColumn =
    UserService.isSuperAdmin() && (props.variant || 'for-me') === 'all';

  return (
    <UpstreamProcessInstanceListTable
      {...(props as any)}
      reportMetadata={
        showTenantColumn
          ? withTenantColumn(props.reportMetadata, t('tenant'))
          : props.reportMetadata
      }
    />
  );
}

export { withTenantColumn };
