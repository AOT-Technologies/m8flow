import { Alert, Box } from '@mui/material';
import CoreProcessGroupForm from '@spiff-core/components/ProcessGroupForm';
import type { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import UserService from '../services/UserService';

type CoreFormProps = ComponentProps<typeof CoreProcessGroupForm>;

/**
 * Keep the upstream process-group form intact and add only the M8Flow tenant
 * gate. The backend still validates the resolved tenant before the write.
 */
export default function TenantScopedProcessGroupForm(props: CoreFormProps) {
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const missingTenantSelection =
    props.mode === 'new' && UserService.isSuperAdmin() && !selectedTenantId;

  return (
    <>
      {missingTenantSelection ? (
        <Alert severity="warning" data-testid="super-admin-tenant-alert">
          {t('select_tenant_before_workflow_management')}
        </Alert>
      ) : null}
      <Box component="fieldset" disabled={missingTenantSelection} sx={{ border: 0, p: 0, m: 0 }}>
        <CoreProcessGroupForm {...props} />
      </Box>
    </>
  );
}
