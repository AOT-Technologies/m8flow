import { Alert, Box } from '@mui/material';
import CoreProcessModelTreePage from '@spiff-core/views/StartProcess/ProcessModelTreePage';
import { MouseEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';

type ProcessModelTreePageProps = {
  setNavElementCallback?: Function;
  navigateToPage?: boolean;
};

const WORKFLOW_CREATE_BUTTONS = [
  'add-process-group-button',
  'add-process-model-button',
];

function isWorkflowCreateButton(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) {
    return false;
  }
  return WORKFLOW_CREATE_BUTTONS.some((testId) =>
    target.closest(`[data-testid="${testId}"]`),
  );
}

function preventUnscopedWorkflowCreate(event: MouseEvent<HTMLElement>) {
  if (!isWorkflowCreateButton(event.target)) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
}

export default function ProcessModelTreePage(props: ProcessModelTreePageProps): ReactNode {
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const requiresTenantSelection = UserService.isSuperAdmin() && !selectedTenantId;

  return (
    <Box onClickCapture={requiresTenantSelection ? preventUnscopedWorkflowCreate : undefined}>
      {requiresTenantSelection && (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="workflow-tenant-selection-alert">
          {t('select_tenant_before_workflow_management')}
        </Alert>
      )}
      <CoreProcessModelTreePage {...props} />
    </Box>
  );
}
