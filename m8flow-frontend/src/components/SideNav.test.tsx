import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import SideNav from './SideNav';

// The one behavior under test: the "Manage Token" nav item is gated on
// POST /m8flow/nats-tokens (manage-nats-tokens, tenant-admin only). It must
// appear when that permission is granted and be hidden otherwise.
const h = vi.hoisted(() => ({
  // (method, uri) => boolean — controls what the mocked ability allows.
  can: ((_method: string, _uri: string) => false) as (
    method: string,
    uri: string,
  ) => boolean,
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: (method: string, uri: string) => h.can(method, uri) },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      processGroupListPath: '/process-groups',
      processInstanceListPath: '/process-instances',
      processInstanceListForMePath: '/process-instances/for-me',
      messageInstanceListPath: '/messages',
      secretListPath: '/secrets',
      serviceTaskListPath: '/service-tasks',
      connectorsGroupedPath: '/m8flow/connectors-grouped',
      m8flowMcpConnectionPath: '/m8flow/mcp-connection',
      m8flowNatsTokensPath: '/m8flow/nats-tokens',
      m8flowTenantManagementPath: '/m8flow/tenant-management',
    },
  })),
}));

vi.mock('../utils/useConfig', () => ({
  useConfig: () => ({
    NATS_MONITORING_ENABLED: false,
    MCP_CONNECTION_ENABLED: false,
  }),
}));

vi.mock('../services/UserService', () => ({
  default: {
    getUserEmail: () => 'user@example.com',
    getPreferredUsername: () => 'user',
    getTenantName: () => 'tenant',
    isSuperAdmin: () => false,
    TENANT_DISPLAY_NAME_UPDATED_EVENT: 'tenant-display-name-updated',
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
      changeLanguage: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
    },
  }),
}));

vi.mock('@spiffworkflow-frontend/helpers/appVersionInfo', () => ({
  default: () => ({}),
}));

vi.mock('@spiffworkflow-frontend/config', () => ({
  DARK_MODE_ENABLED: false,
  DOCUMENTATION_URL: '',
  SPIFF_ENVIRONMENT: 'test',
}));

vi.mock('./SpiffLogo', () => ({ default: () => null }));
vi.mock('./GlobalTenantSelector', () => ({ default: () => null }));
vi.mock('@spiffworkflow-frontend/components/SpiffTooltip', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@spiffworkflow-frontend/components/ExtensionUxElementForDisplay', () => ({
  default: () => null,
}));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      has: () => true,
    },
  );
});

const renderNav = () =>
  render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter>
        <SideNav
          isCollapsed={false}
          onToggleCollapse={() => {}}
          onToggleDarkMode={() => {}}
          isDark={false}
          setAdditionalNavElement={() => {}}
        />
      </MemoryRouter>
    </ThemeProvider>,
  );

describe('SideNav Manage Token gating', () => {
  beforeEach(() => {
    // jsdom has no matchMedia; MUI's useMediaQuery needs it.
    if (!window.matchMedia) {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as unknown as typeof window.matchMedia;
    }
    h.can = () => false;
  });

  it('shows the Manage Token item when POST /m8flow/nats-tokens is allowed', () => {
    h.can = (method, uri) =>
      method === 'POST' && uri === '/m8flow/nats-tokens';
    renderNav();
    expect(screen.getByTestId('nav-item-manageToken')).toBeInTheDocument();
  });

  it('hides the Manage Token item when the manage permission is absent', () => {
    // Read-only (GET) on the same path must NOT surface the management item.
    h.can = (method, uri) => method === 'GET' && uri === '/m8flow/nats-tokens';
    renderNav();
    expect(screen.queryByTestId('nav-item-manageToken')).not.toBeInTheDocument();
  });
});
