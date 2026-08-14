import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type React from 'react';
import ProcessInstanceListTabs from './ProcessInstanceListTabs';

const h = vi.hoisted(() => ({
  can: ((_method: string, _uri: string) => false) as (
    method: string,
    uri: string,
  ) => boolean,
  permissionsLoaded: true,
  navigate: vi.fn(),
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: (method: string, uri: string) => h.can(method, uri) },
    permissionsLoaded: h.permissionsLoaded,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      processInstanceListPath: '/process-instances',
      processInstanceListForMePath: '/process-instances/for-me',
      m8flowTenantListPath: '/m8flow/tenants',
    },
  })),
}));

vi.mock('./SpiffTooltip', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => h.navigate };
});

import UserService from '../services/UserService';

const theme = createTheme();

function allowAllTabs() {
  h.can = (method, uri) => {
    if (method === 'GET' && uri === '/process-instances') return true;
    if (method === 'POST' && uri === '/process-instances/for-me') return true;
    return false;
  };
}

function renderTabs(variant: string) {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <ProcessInstanceListTabs variant={variant} />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('ProcessInstanceListTabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.navigate = vi.fn();
    h.permissionsLoaded = true;
    allowAllTabs();
  });

  it('hides for-me and redirects to all when the user is super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderTabs('for-me');
    expect(
      screen.queryByTestId('process-instance-list-for-me'),
    ).toBeNull();
    expect(screen.getByTestId('process-instance-list-all')).toBeInTheDocument();
    expect(h.navigate).toHaveBeenCalledWith('/process-instances/all', {
      replace: true,
    });
  });

  it('hides for-me and redirects to all when GET tenant list is granted', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    h.can = (method, uri) => {
      if (method === 'GET' && uri === '/m8flow/tenants') return true;
      if (method === 'GET' && uri === '/process-instances') return true;
      if (method === 'POST' && uri === '/process-instances/for-me') return true;
      return false;
    };
    renderTabs('for-me');
    expect(
      screen.queryByTestId('process-instance-list-for-me'),
    ).toBeNull();
    expect(h.navigate).toHaveBeenCalledWith('/process-instances/all', {
      replace: true,
    });
  });

  it('keeps for-me for a non-cross-tenant user', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderTabs('for-me');
    expect(
      screen.getByTestId('process-instance-list-for-me'),
    ).toBeInTheDocument();
    expect(h.navigate).not.toHaveBeenCalledWith('/process-instances/all', {
      replace: true,
    });
  });
});
