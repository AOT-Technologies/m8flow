/**
 * Breadcrumb shell — disables navigation when the user cannot list process groups.
 */
import { Box } from '@mui/material';
import UpstreamBreadcrumb from '@spiff-core/components/ProcessBreadcrumb';
import { usePermissionFetcher } from '../hooks/PermissionService';
import type { HotCrumbItem } from '@spiffworkflow-frontend/interfaces';

export default function ProcessBreadcrumb({
  hotCrumbs,
}: {
  hotCrumbs?: HotCrumbItem[];
}) {
  const path = '/v1.0/process-groups';
  const { ability, permissionsLoaded } = usePermissionFetcher({
    [path]: ['GET'],
  });

  const interactive =
    permissionsLoaded && ability.can('GET', path);

  if (interactive) {
    return <UpstreamBreadcrumb hotCrumbs={hotCrumbs} />;
  }

  return (
    <Box
      sx={{
        pointerEvents: 'none',
        '& a': { color: 'text.primary', textDecoration: 'none' },
      }}
    >
      <UpstreamBreadcrumb hotCrumbs={hotCrumbs} />
    </Box>
  );
}
