/**
 * Tenant display chip for non–super-admin users (expanded + collapsed).
 */
import { Box, Stack, Tooltip, Typography } from '@mui/material';
import { CorporateFare } from '@mui/icons-material';

type ExpandedProps = {
  tenantLabel: string;
  caption: string;
};

export function SideNavTenantBadgeExpanded({
  tenantLabel,
  caption,
}: ExpandedProps) {
  return (
    <Tooltip
      title={tenantLabel}
      placement="bottom"
      enterDelay={500}
      enterNextDelay={300}
    >
      <Stack
        data-testid="nav-tenant-name"
        direction="row"
        alignItems="center"
        spacing={1}
        onClick={(event) => event.stopPropagation()}
        sx={{
          mt: 1.5,
          px: 1.25,
          py: 0.5,
          width: '100%',
          bgcolor: 'background.light',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1.5,
          cursor: 'default',
          userSelect: 'none',
        }}
      >
        <CorporateFare
          sx={{
            fontSize: '1.1rem',
            color: 'primary.main',
            flexShrink: 0,
          }}
        />
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              display: 'block',
              lineHeight: 1.2,
              fontSize: '0.625rem',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'text.secondary',
            }}
          >
            {caption}
          </Typography>
          <Typography
            variant="body2"
            noWrap
            sx={{ fontWeight: 600, lineHeight: 1.3 }}
          >
            {tenantLabel}
          </Typography>
        </Box>
      </Stack>
    </Tooltip>
  );
}

type CollapsedProps = {
  tenantLabel: string;
  caption: string;
};

export function SideNavTenantBadgeCollapsed({
  tenantLabel,
  caption,
}: CollapsedProps) {
  return (
    <Tooltip title={`${caption}: ${tenantLabel}`} placement="right">
      <Box
        data-testid="nav-tenant-name-collapsed"
        sx={{
          display: 'flex',
          justifyContent: 'center',
          mb: 1,
          color: 'text.secondary',
        }}
      >
        <CorporateFare sx={{ fontSize: '1.25rem' }} />
      </Box>
    </Tooltip>
  );
}
