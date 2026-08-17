/**
 * PI list with filters — upstream + SA global-tenant filter injection.
 */
import { useMemo } from 'react';
import Upstream from '@spiff-core/components/ProcessInstanceListTableWithFilters';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import UserService from '../services/UserService';

export default function ProcessInstanceListTableWithFilters(props: Record<string, any>) {
  const sa = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();

  const filters = useMemo(() => {
    const incoming = props.additionalReportFilters as
      | Array<{ field_name: string; field_value?: string; operator?: string }>
      | undefined;
    if (!(sa && selectedTenantId)) return incoming;
    const withoutTenant = (incoming || []).filter((f) => f.field_name !== 'tenant_id');
    return [
      ...withoutTenant,
      {
        field_name: 'tenant_id',
        field_value: selectedTenantId,
        operator: 'equals',
      },
    ];
  }, [props.additionalReportFilters, sa, selectedTenantId]);

  const { showStatusChart: _ignored, ...rest } = props;

  return (
    <Upstream
      {...rest}
      key={sa ? `t:${selectedTenantId || '*'}` : 'std'}
      additionalReportFilters={filters}
    />
  );
}
