import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import Connectors from './Connectors';

const h = vi.hoisted(() => ({
  connectorsResponse: [] as any[],
  profilesResponse: [] as any[],
  navigate: (() => {}) as (...args: any[]) => void,
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET' },
    makeCallToBackend: vi.fn((opts: any) => {
      if (opts.path === '/m8flow/connectors-grouped') {
        opts.successCallback(h.connectorsResponse);
      }
      if (opts.path?.startsWith('/m8flow/connector-profiles')) {
        opts.successCallback(h.profilesResponse);
      }
    }),
  },
}));

// One shared ability object, as the real hook does: it reads a stable instance
// out of AbilityContext and mutates it in place. Returning a new object literal
// per call would make every `ability`-dependent effect re-run on each render --
// an endless fetch/setState/render loop, not a component bug.
const mockAbility = { can: () => true };

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: mockAbility,
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      connectorsGroupedPath: '/m8flow/connectors-grouped',
      connectorProfileListPath: '/m8flow/connector-profiles',
    },
  })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => h.navigate };
});

vi.mock('@casl/react', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../utils/connectorCardDisplay', () => ({
  ConnectorNameAvatar: () => <span data-testid="avatar" />,
}));

vi.mock('../components/ConnectorOperationsModal', () => ({
  default: () => null,
}));

vi.mock('../helpers', () => ({ setPageTitle: vi.fn() }));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        // Must NOT return a function for `then` (or symbols) or the mocked
        // module namespace looks like a never-resolving thenable and vitest
        // hangs awaiting it during collection.
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      // vitest validates accessed exports with `prop in module` and throws
      // "No <name> export is defined" otherwise — report every icon as present.
      has: () => true,
    },
  );
});

const base = {
  description: '',
  status: 'available',
  icon: 'extension',
  operationCount: 1,
  operations: [],
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <Connectors />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.navigate = vi.fn();
  h.profilesResponse = [];
  h.connectorsResponse = [
    { ...base, id: 'github', name: 'GitHub', supportsProfiles: true },
    { ...base, id: 'http', name: 'HTTP', supportsProfiles: false },
  ];
});

describe('Connectors configure navigation', () => {
  it('routes a profile-capable connector to its profile list', async () => {
    renderPage();
    const btn = await screen.findByTestId('connector-configure-github');
    fireEvent.click(btn);
    await waitFor(() =>
      expect(h.navigate).toHaveBeenCalledWith('/connectors/github/profiles'),
    );
  });

  it('routes a connector with no profile fields to the generic secrets page', async () => {
    renderPage();
    const btn = await screen.findByTestId('connector-configure-http');
    fireEvent.click(btn);
    await waitFor(() =>
      expect(h.navigate).toHaveBeenCalledWith('/configuration/secrets'),
    );
  });

  it('offers only one configuration action per connector', async () => {
    renderPage();
    await screen.findByTestId('connector-configure-github');
    // The separate "Profiles" button is gone: Configure is the single entry
    // point, so a user is never asked to choose between two config methods.
    expect(screen.queryByTestId('connector-profiles-github')).toBeNull();
  });

  it('shows the profile count on the Configure button when profiles exist', async () => {
    h.profilesResponse = [
      { connector_type: 'github', profile_name: 'default' },
      { connector_type: 'github', profile_name: 'staging' },
    ];
    renderPage();
    const btn = await screen.findByTestId('connector-configure-github');
    await waitFor(() =>
      expect(btn.textContent).toBe('connector_configure_count'),
    );
    // A connector with no profiles keeps the plain label.
    expect(
      (await screen.findByTestId('connector-configure-http')).textContent,
    ).toBe('configure');
  });
});
