import React, { useState } from 'react';
import {
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Popover,
  List,
  ListItemButton,
  ListItemText,
  Typography,
} from '@mui/material';
import { Business } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import UserService from '../services/UserService';
import { useTenants } from '../hooks/useTenants';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import SpiffTooltip from '@spiffworkflow-frontend/components/SpiffTooltip';

type Props = {
  isCollapsed: boolean;
};

export default function GlobalTenantSelector({ isCollapsed }: Props) {
  const { t } = useTranslation();
  const isSuperAdmin = UserService.isSuperAdmin();
  const { data: tenants = [] } = useTenants(isSuperAdmin);
  const { selectedTenantId, setSelectedTenantId } = useGlobalTenant();
  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);

  if (!isSuperAdmin || tenants.length === 0) {
    return null;
  }

  const selectedTenant = tenants.find((t) => t.id === selectedTenantId);
  const selectedLabel = selectedTenant?.name ?? t('all_tenants', 'All Tenants');

  if (isCollapsed) {
    return (
      <>
        <SpiffTooltip title={selectedLabel} placement="right">
          <IconButton
            size="small"
            onClick={(e) => setAnchorEl(e.currentTarget)}
            sx={{ mx: 'auto', display: 'flex' }}
            data-testid="global-tenant-selector-collapsed"
          >
            <Business fontSize="small" color={selectedTenantId ? 'primary' : 'inherit'} />
          </IconButton>
        </SpiffTooltip>
        <Popover
          open={Boolean(anchorEl)}
          anchorEl={anchorEl}
          onClose={() => setAnchorEl(null)}
          anchorOrigin={{ vertical: 'center', horizontal: 'right' }}
          transformOrigin={{ vertical: 'center', horizontal: 'left' }}
        >
          <List dense sx={{ minWidth: 160 }}>
            <ListItemButton
              selected={selectedTenantId === ''}
              onClick={() => { setSelectedTenantId(''); setAnchorEl(null); }}
            >
              <ListItemText primary={t('all_tenants', 'All Tenants')} />
            </ListItemButton>
            {tenants.map((tenant) => (
              <ListItemButton
                key={tenant.id}
                selected={selectedTenantId === tenant.id}
                onClick={() => { setSelectedTenantId(tenant.id); setAnchorEl(null); }}
              >
                <ListItemText primary={tenant.name} />
              </ListItemButton>
            ))}
          </List>
        </Popover>
      </>
    );
  }

  return (
    <Box sx={{ px: 1, pb: 0.5 }} data-testid="global-tenant-selector">
      <FormControl fullWidth size="small">
        <InputLabel id="global-tenant-label" shrink sx={{ fontSize: '0.75rem' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Business sx={{ fontSize: '0.9rem' }} />
            <Typography variant="caption">{t('tenant')}</Typography>
          </Box>
        </InputLabel>
        <Select
          labelId="global-tenant-label"
          value={selectedTenantId}
          displayEmpty
          notched
          renderValue={() => selectedLabel}
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Business sx={{ fontSize: '0.9rem' }} />
              <Typography variant="caption">{t('tenant')}</Typography>
            </Box>
          }
          onChange={(e) => setSelectedTenantId(e.target.value as string)}
          sx={{
            fontSize: '0.75rem',
            '& .MuiSelect-select': {
              py: 0.5,
              minHeight: 'unset',
            },
          }}
          data-testid="global-tenant-select"
        >
          <MenuItem value="" sx={{ fontSize: '0.75rem' }}>
            <em>{t('all_tenants', 'All Tenants')}</em>
          </MenuItem>
          {tenants.map((tenant) => (
            <MenuItem key={tenant.id} value={tenant.id} sx={{ fontSize: '0.75rem' }}>
              {tenant.name}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  );
}
