import { useEffect } from 'react';
import { Alert, Box } from '@mui/material';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import useAPIError from '@spiffworkflow-frontend/hooks/UseApiError';
import { ProcessInstance } from '../../interfaces';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import { modifyProcessIdentifierForPathParam } from '../../helpers';
import HttpService from '../../services/HttpService';
import UserService from '../../services/UserService';

export default function StartProcessInstance() {
  const { t } = useTranslation();
  const { modifiedProcessModelId } = useParams<{
    modifiedProcessModelId: string;
  }>();
  const navigate = useNavigate();
  const { addError } = useAPIError();
  const { selectedTenantId } = useGlobalTenant();
  const missingTenantSelection =
    UserService.isSuperAdmin() && !selectedTenantId;

  const modifiedProcessModelIdParam = modifyProcessIdentifierForPathParam(
    modifiedProcessModelId || '',
  );

  const onProcessInstanceRun = (processInstance: ProcessInstance) => {
    const processInstanceId = processInstance.id;
    if (processInstance.process_model_uses_queued_execution) {
      navigate(
        `/process-instances/for-me/${modifiedProcessModelIdParam}/${processInstanceId}/progress`,
      );
    } else {
      navigate(
        `/process-instances/for-me/${modifiedProcessModelIdParam}/${processInstanceId}/interstitial`,
      );
    }
  };

  const processModelRun = (processInstance: ProcessInstance) => {
    HttpService.makeCallToBackend({
      path: `/process-instance-run/${modifiedProcessModelIdParam}/${processInstance.id}`,
      successCallback: onProcessInstanceRun,
      failureCallback: (result: any) => {
        addError(result);
      },
      httpMethod: 'POST',
    });
  };

  const processInstanceCreateAndRun = () => {
    HttpService.makeCallToBackend({
      path: `/v1.0/process-instances/${modifiedProcessModelIdParam}`,
      successCallback: processModelRun,
      failureCallback: (result: any) => {
        addError(result);
      },
      httpMethod: 'POST',
    });
  };

  useEffect(() => {
    if (missingTenantSelection) {
      return;
    }
    processInstanceCreateAndRun();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missingTenantSelection]);

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
