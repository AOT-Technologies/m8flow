import { Box } from '@mui/material';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { HotCrumbItem } from '@spiffworkflow-frontend/interfaces';
import CoreProcessBreadcrumb from '@spiffworkflow-frontend/components/ProcessBreadcrumb';

type OwnProps = {
  hotCrumbs?: HotCrumbItem[];
};

export default function ProcessBreadcrumb({ hotCrumbs }: OwnProps) {
  const { ability, permissionsLoaded } = usePermissionFetcher({
    '/v1.0/process-groups': ['GET'],
  });

  const canReadProcessGroups =
    permissionsLoaded && ability.can('GET', '/v1.0/process-groups');

  if (!canReadProcessGroups) {
    return (
      <Box
        sx={{
          pointerEvents: 'none',
          '& a': { color: 'text.primary', textDecoration: 'none' },
        }}
      >
        <CoreProcessBreadcrumb hotCrumbs={hotCrumbs} />
      </Box>
    );
  }

  return <CoreProcessBreadcrumb hotCrumbs={hotCrumbs} />;
}
