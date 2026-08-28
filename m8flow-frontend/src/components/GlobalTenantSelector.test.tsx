import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import GlobalTenantSelector from './GlobalTenantSelector';
import {
  GlobalTenantProvider,
  GLOBAL_TENANT_STORAGE_KEY,
} from '../contexts/GlobalTenantContext';

const h = vi.hoisted(() => ({
  useTenants: vi.fn(),
  isSuperAdmin: vi.fn(() => true),
}));

vi.mock('../hooks/useTenants', () => ({
  useTenants: h.useTenants,
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: h.isSuperAdmin,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock('@spiffworkflow-frontend/components/SpiffTooltip', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@mui/icons-material', () => ({
  Business: () => null,
}));

function renderSelector() {
  return render(
    <ThemeProvider theme={createTheme()}>
      <GlobalTenantProvider>
        <GlobalTenantSelector isCollapsed={false} />
      </GlobalTenantProvider>
    </ThemeProvider>,
  );
}

describe('GlobalTenantSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    h.isSuperAdmin.mockReturnValue(true);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('clears a persisted tenant selection when that tenant no longer exists', async () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'deleted-tenant');
    h.useTenants.mockReturnValue({
      data: [{ id: 'tenant-a', name: 'Acme Corp' }],
    });

    renderSelector();

    await waitFor(() => {
      expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBeNull();
    });
    expect(screen.getByTestId('global-tenant-select')).toHaveTextContent(
      'All Tenants',
    );
  });

  it('keeps a persisted tenant selection when the tenant still exists', async () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'tenant-a');
    h.useTenants.mockReturnValue({
      data: [{ id: 'tenant-a', name: 'Acme Corp' }],
    });

    renderSelector();

    await waitFor(() => {
      expect(screen.getByTestId('global-tenant-select')).toHaveTextContent(
        'Acme Corp',
      );
    });
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBe('tenant-a');
  });
});
