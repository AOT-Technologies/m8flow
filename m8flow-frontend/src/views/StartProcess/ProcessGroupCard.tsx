/** Process group card with optional super-admin tenant chip. */
import { Box, Chip } from '@mui/material';
import UpstreamCard from '@spiff-core/views/StartProcess/ProcessGroupCard';
import UserService from '../../services/UserService';

export default function ProcessGroupCard(props: {
  group: { id: string; tenantName?: string; [k: string]: unknown };
  [k: string]: unknown;
}) {
  const label = props.group.tenantName;
  if (!(UserService.isSuperAdmin() && label)) {
    return <UpstreamCard {...(props as any)} />;
  }
  return (
    <Box sx={{ position: 'relative', height: '100%' }}>
      <Chip
        size="small"
        label={label}
        data-testid={`process-group-tenant-chip-${props.group.id}`}
        sx={{ position: 'absolute', top: 12, right: 12, zIndex: 1 }}
      />
      <UpstreamCard {...(props as any)} />
    </Box>
  );
}
