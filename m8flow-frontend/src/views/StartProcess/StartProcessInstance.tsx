import { Alert, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import HttpService from '../../services/HttpService';
import useAPIError from '../../hooks/UseApiError';
import { modifyProcessIdentifierForPathParam } from '../../helpers';
import type { ProcessInstance } from '../../interfaces';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';

export default function StartProcessInstance() {
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const { modifiedProcessModelId } = useParams<{ modifiedProcessModelId: string }>();
  const navigate = useNavigate();
  const { addError } = useAPIError();
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

  const modelId = modifyProcessIdentifierForPathParam(modifiedProcessModelId || '');
  const onRun = (processInstance: ProcessInstance) => {
    HttpService.makeCallToBackend({
      path: `/process-instance-run/${modelId}/${processInstance.id}`,
      successCallback: (result: ProcessInstance) => {
        const suffix = result.process_model_uses_queued_execution ? 'progress' : 'interstitial';
        navigate(`/process-instances/for-me/${modelId}/${result.id}/${suffix}`);
      },
      failureCallback: addError,
      httpMethod: 'POST',
      tenantId: selectedTenantId,
    });
  };

  useEffect(() => {
    HttpService.makeCallToBackend({
      path: `/v1.0/process-instances/${modelId}`,
      successCallback: onRun,
      failureCallback: addError,
      httpMethod: 'POST',
      tenantId: selectedTenantId,
    });
    // The selected tenant is intentionally captured for this one start action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
