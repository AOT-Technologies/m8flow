import { Alert, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useEffect, useRef } from 'react';
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
  const startedTargets = useRef(new Set<string>());
  const modelId = modifyProcessIdentifierForPathParam(modifiedProcessModelId || '');

  useEffect(() => {
    if (missingTenantSelection) {
      return;
    }

    const target = `${modelId}:${selectedTenantId || ''}`;
    if (startedTargets.current.has(target)) {
      return;
    }
    startedTargets.current.add(target);

    HttpService.makeCallToBackend({
      path: `/v1.0/process-instances/${modelId}`,
      successCallback: (processInstance: ProcessInstance) => {
        HttpService.makeCallToBackend({
          path: `/process-instance-run/${modelId}/${processInstance.id}`,
          successCallback: (result: ProcessInstance) => {
            const suffix = result.process_model_uses_queued_execution
              ? 'progress'
              : 'interstitial';
            navigate(`/process-instances/for-me/${modelId}/${result.id}/${suffix}`);
          },
          failureCallback: addError,
          httpMethod: 'POST',
          tenantId: selectedTenantId,
        });
      },
      failureCallback: addError,
      httpMethod: 'POST',
      tenantId: selectedTenantId,
    });
  }, [addError, missingTenantSelection, modelId, navigate, selectedTenantId]);

  if (missingTenantSelection) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning" data-testid="start-process-tenant-alert">
          {t('select_tenant_before_workflow_management')}
        </Alert>
      </Box>
    );
  }

  return null;
}
