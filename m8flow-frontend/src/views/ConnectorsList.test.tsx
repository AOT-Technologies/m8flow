import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConnectorsList from './ConnectorsList';

const mockMakeCallToBackend = vi.fn();

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: (...args: unknown[]) => mockMakeCallToBackend(...args),
  },
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: () => ({
    targetUris: {
      serviceTaskListPath: '/v1.0/service-tasks',
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
      };
      return strings[key] ?? key;
    },
  }),
}));

describe('ConnectorsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls backend with configured serviceTaskListPath, not a hardcoded path', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback([]);
    });

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

    await waitFor(() => {
      expect(screen.getByText('HTTP Connector')).toBeInTheDocument();
    });
    expect(screen.getByText('2 operations')).toBeInTheDocument();
  });

  it('groups operators from an array of objects', async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }: { successCallback: (r: unknown) => void }) => {
      successCallback([{ id: 'smtp_v1/send' }]);
    });

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

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

    render(<ConnectorsList />);

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Unable to load connectors.')).toBeInTheDocument();
  });
});
