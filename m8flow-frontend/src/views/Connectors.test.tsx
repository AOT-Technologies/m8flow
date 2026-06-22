import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import Connectors from './Connectors';

const h = vi.hoisted(() => ({
  connectorsResponse: [] as any[],
  navigate: (() => {}) as (...args: any[]) => void,
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET' },
    makeCallToBackend: vi.fn((opts: any) => {
      if (opts.path === '/m8flow/connectors-grouped') {
        opts.successCallback(h.connectorsResponse);
      }
    }),
  },
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => true },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      connectorsGroupedPath: '/m8flow/connectors-grouped',
      secretListPath: '/secrets',
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

vi.mock('@mui/icons-material', () => new Proxy({}, { get: () => () => null }));

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
  h.connectorsResponse = [
    {
      ...base,
      id: 'github',
      name: 'GitHub',
      configFields: [
        { id: 'pat_token', secretKey: 'GITHUB_PAT_TOKEN', label: 'PAT', type: 'password', required: true },
      ],
    },
    { ...base, id: 'http', name: 'HTTP' },
  ];
});

describe('Connectors configure navigation', () => {
  it('routes connectors with configFields to the configure form', async () => {
    renderPage();
    const btn = await screen.findByTestId('connector-configure-github');
    fireEvent.click(btn);
    await waitFor(() =>
      expect(h.navigate).toHaveBeenCalledWith('/connectors/github/configure'),
    );
  });

  it('routes connectors without configFields to the generic secrets page', async () => {
    renderPage();
    const btn = await screen.findByTestId('connector-configure-http');
    fireEvent.click(btn);
    await waitFor(() =>
      expect(h.navigate).toHaveBeenCalledWith('/configuration/secrets'),
    );
  });
});
