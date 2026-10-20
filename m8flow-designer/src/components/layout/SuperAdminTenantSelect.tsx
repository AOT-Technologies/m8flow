import { useTranslation } from 'react-i18next';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { SidebarTenant } from './Sidebar';

const ALL_TENANTS = '__all__';

/** Super-admin tenant picker; its own module so Radix Select stays out of the first-load bundle. */
export function SuperAdminTenantSelect({
  tenants,
  selectedTenantId,
  onTenantChange,
}: {
  tenants: SidebarTenant[];
  selectedTenantId: string | null;
  onTenantChange?: (tenantId: string | null) => void;
}) {
  const { t } = useTranslation();
  // Radix Select items can't carry an empty-string value, so "All tenants" (null) round-trips through a sentinel.
  return (
    <Select
      value={selectedTenantId ?? ALL_TENANTS}
      onValueChange={(value) => onTenantChange?.(value === ALL_TENANTS ? null : value)}
    >
      <SelectTrigger aria-label={t('shell.tenant.label')} className="h-9 bg-sidebar">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_TENANTS}>{t('shell.tenant.allTenants')}</SelectItem>
        {tenants.map((tenant) => (
          <SelectItem key={tenant.id} value={tenant.id}>
            {tenant.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
