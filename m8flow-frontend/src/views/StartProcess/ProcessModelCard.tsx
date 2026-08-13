/**
 * Process model card — upstream body + super-admin tenant chip overlay.
 */
import { Box, Chip } from '@mui/material';
import UpstreamCard from '@spiff-core/views/StartProcess/ProcessModelCard';
import UserService from '../../services/UserService';

export default function ProcessModelCard(props: {
  model: { id: string; tenantName?: string; [k: string]: unknown };
  [k: string]: unknown;
}) {
  const label = props.model.tenantName;
  if (!(UserService.isSuperAdmin() && label)) {
    return <UpstreamCard {...(props as any)} />;
  }
  return (
    <Box sx={{ position: 'relative', height: '100%' }}>
      <Chip
        size="small"
        label={label}
        data-testid={`process-model-tenant-chip-${props.model.id}`}
        sx={{ position: 'absolute', top: 12, right: 12, zIndex: 1 }}
      />
      <UpstreamCard {...(props as any)} />
    </Box>
  );
}
