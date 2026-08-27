import { Alert, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CoreStartProcessInstance from '@spiff-core/views/StartProcess/StartProcessInstance';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';

export default function StartProcessInstance() {
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const missingTenantSelection =
    UserService.isSuperAdmin() && !selectedTenantId;

  if (missingTenantSelection) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning" data-testid="start-process-tenant-alert">
          {t('select_tenant_before_workflow_management')}
        </Alert>
      </Box>
    );
  }

  return <CoreStartProcessInstance />;
}
