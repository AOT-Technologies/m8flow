import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import HeaderTabs from './HeaderTabs';

const h = vi.hoisted(() => ({
  can: ((_method: string, _uri: string) => false) as (
    method: string,
    uri: string,
  ) => boolean,
  permissionsLoaded: true,
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

vi.mock('../hooks/UriListForPermissions', () => ({
  useUriListForPermissions: vi.fn(() => ({
    targetUris: {
      processInstanceListForMePath: '/process-instances/for-me',
    },
  })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../services/UserService';

const theme = createTheme();

function renderTabs() {
  return render(
    <ThemeProvider theme={theme}>
      <HeaderTabs
        value={0}
        onChange={() => {}}
        taskControlElement={<div data-testid="task-controls" />}
      />
    </ThemeProvider>,
  );
}

describe('HeaderTabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.can = () => false;
    h.permissionsLoaded = true;
  });

  it('renders nothing until permissions load', () => {
    h.permissionsLoaded = false;
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderTabs();
    expect(screen.queryByTestId('tab-tasks-assigned-to-me')).toBeNull();
  });

  it('uses the tasks label and omits workflows_created_by_me for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    h.can = () => true;
    renderTabs();
    expect(screen.getByTestId('tab-tasks-assigned-to-me')).toHaveTextContent(
      'tasks',
    );
    expect(
      screen.queryByTestId('tab-workflows-created-by-me'),
    ).toBeNull();
  });

  it('shows workflows_created_by_me for non-super-admin with POST permission', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    h.can = (method, uri) =>
      method === 'POST' && uri === '/process-instances/for-me';
    renderTabs();
    expect(screen.getByTestId('tab-tasks-assigned-to-me')).toHaveTextContent(
      'tasks_assigned_to_me',
    );
    expect(
      screen.getByTestId('tab-workflows-created-by-me'),
    ).toHaveTextContent('workflows_created_by_me');
  });

  it('hides workflows_created_by_me for non-super-admin without POST permission', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    h.can = () => false;
    renderTabs();
    expect(screen.getByTestId('tab-tasks-assigned-to-me')).toBeInTheDocument();
    expect(
      screen.queryByTestId('tab-workflows-created-by-me'),
    ).toBeNull();
  });
});
