import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConnectorsList from './ConnectorsList';

const mockMakeCallToBackend = vi.fn();
const mockUsePermissionFetcher = vi.fn();

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: (...args: unknown[]) => mockMakeCallToBackend(...args),
  },
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: () => mockUsePermissionFetcher(),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: () => ({
    targetUris: {
      serviceTaskListPath: '/v1.0/service-tasks',
      secretListPath: '/secrets',
    },
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) => {
      if (key === 'available_operations_count') {
        const c = opts?.count ?? 0;
        return c === 1 ? `${c} operation` : `${c} operations`;
      }
      const strings: Record<string, string> = {
        connectors: 'Connectors',
        connectors_description: 'Use these connectors via Service Tasks.',
        connector_usage_hint: 'Use in a Service Task in your process model.',
        unable_to_load_connectors: 'Unable to load connectors.',
        connectors_unauthorized: 'You do not have permission to view connectors.',
        connectors_unavailable: 'Connectors service is currently unavailable.',
        no_connectors_available: 'No connectors are currently available.',
        configure: 'Configure',
      };
      return strings[key] ?? key;
    },
  }),
}));

function renderConnectorsList() {
  return render(
    <MemoryRouter>
      <ConnectorsList />
    </MemoryRouter>,
  );
}

describe('ConnectorsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });
  });

  it('calls backend with configured serviceTaskListPath, not a hardcoded path', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback([]);
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(mockMakeCallToBackend).toHaveBeenCalledWith(
        expect.objectContaining({ path: '/v1.0/service-tasks' }),
      );
    });
    expect(mockMakeCallToBackend).not.toHaveBeenCalledWith(
      expect.objectContaining({ path: '/service-tasks' }),
    );
  });

  it('groups operators from an array of string ids', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback(['http_connector_v2/get', 'http_connector_v2/post']);
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    expect(screen.getByText('2 operations')).toBeInTheDocument();
  });

  it('groups operators from an array of objects', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback([{ id: 'smtp_v1/send' }]);
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('SMTP')).toBeInTheDocument();
    });
    expect(screen.getByText('1 operation')).toBeInTheDocument();
  });

  it('normalizes object payload with items array', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback({
        items: ['http_connector_v2/get', 'http_connector_v2/post'],
      });
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    expect(screen.getByText('2 operations')).toBeInTheDocument();
  });

  it('normalizes object payload with results array', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback({
        results: [{ id: 'api_v1/list' }, { id: 'api_v1/create' }],
      });
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('API')).toBeInTheDocument();
    });
    expect(screen.getByText('2 operations')).toBeInTheDocument();
  });

  it('normalizes keyed object map with connector ids', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback({
        http_connector_v2: [{ id: 'http_connector_v2/send' }],
      });
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    expect(screen.getByText('1 operation')).toBeInTheDocument();
  });

  it('shows unavailable message and hides spinner on 503 failure', async () => {
    mockMakeCallToBackend.mockImplementation(
      ({ failureCallback }: { failureCallback: (e: unknown) => void }) => {
        failureCallback({ status_code: 503 });
      },
    );

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
    expect(
      screen.getByText('Connectors service is currently unavailable.'),
    ).toBeInTheDocument();
  });

  it('shows unauthorized message on 403 failure', async () => {
    mockMakeCallToBackend.mockImplementation(
      ({ failureCallback }: { failureCallback: (e: unknown) => void }) => {
        failureCallback({ status_code: 403 });
      },
    );

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
    expect(
      screen.getByText('You do not have permission to view connectors.'),
    ).toBeInTheDocument();
  });

  it('shows generic load failure when status is unknown', async () => {
    mockMakeCallToBackend.mockImplementation(
      ({ failureCallback }: { failureCallback: (e: unknown) => void }) => {
        failureCallback({ message: 'oops' });
      },
    );

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Unable to load connectors.')).toBeInTheDocument();
  });

  it('shows Configure link to secrets when user has GET /secrets', async () => {
    mockUsePermissionFetcher.mockReturnValue({
      ability: {
        can: (method: string, uri: string) =>
          method === 'GET' && uri === '/secrets',
      },
      permissionsLoaded: true,
    });
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback(['http_connector_v2/get']);
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    const btn = screen.getByTestId('connector-configure-http_connector_v2');
    expect(btn).toHaveAttribute('href', '/configuration/secrets');
    expect(btn).toHaveTextContent('Configure');
  });

  it('hides Configure when user lacks GET /secrets', async () => {
    mockUsePermissionFetcher.mockReturnValue({
      ability: {
        can: (method: string, uri: string) => {
          if (method === 'GET' && uri === '/secrets') return false;
          return true;
        },
      },
      permissionsLoaded: true,
    });
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback(['http_connector_v2/get']);
    });

    renderConnectorsList();

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId('connector-configure-http_connector_v2'),
    ).not.toBeInTheDocument();
  });
});
