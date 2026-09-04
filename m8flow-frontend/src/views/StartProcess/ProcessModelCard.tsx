import { Box, Chip } from '@mui/material';
import CoreProcessModelCard from '@spiff-core/views/StartProcess/ProcessModelCard';
import type { ComponentProps, MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';
import { getProcessTenantLabel } from './processTenantLabelRegistry';

type ProcessModelCardProps = ComponentProps<typeof CoreProcessModelCard> & {
  model: ComponentProps<typeof CoreProcessModelCard>['model'] & {
    tenantName?: string;
  };
};

export default function ProcessModelCard({
  model,
  ...coreProps
}: ProcessModelCardProps) {
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const tenantLabel = model.tenantName || getProcessTenantLabel(model.id);
  const showTenantChip = UserService.isSuperAdmin() && Boolean(tenantLabel);
  const requiresTenantSelection = UserService.isSuperAdmin() && !selectedTenantId;

  const preventUnscopedStart = (event: MouseEvent<HTMLDivElement>) => {
    if (
      requiresTenantSelection &&
      event.target instanceof Element &&
      event.target.closest('.MuiCardActions-root button')
    ) {
      event.preventDefault();
      event.stopPropagation();
    }
  };

  return (
    <Box
      sx={{
        position: 'relative',
        height: '100%',
        ...(requiresTenantSelection && {
          '& .MuiCardActions-root button': {
            cursor: 'not-allowed',
            opacity: 0.5,
          },
        }),
      }}
      onClickCapture={preventUnscopedStart}
      aria-label={
        requiresTenantSelection
          ? t('select_tenant_before_workflow_management')
          : undefined
      }
    >
      {showTenantChip ? (
        <Chip
          size="small"
          label={tenantLabel}
          data-testid={`process-model-tenant-chip-${model.id}`}
          sx={{ position: 'absolute', top: 12, right: 12, zIndex: 1 }}
        />
      ) : null}
      <CoreProcessModelCard model={model} {...coreProps} />
    </Box>
  );
}
