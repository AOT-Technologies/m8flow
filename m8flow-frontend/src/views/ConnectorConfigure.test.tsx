import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import ConnectorConfigure, { secretKeyFor } from './ConnectorConfigure';

// Shared, mutable state the hoisted mocks read from. Each test sets these in
// beforeEach / inline before rendering.
const h = vi.hoisted(() => ({
  connectorsResponse: [] as any[],
  secretsPages: {} as Record<string, any>,
  params: { connectorId: 'github' } as Record<string, string>,
  navigate: (() => {}) as (...args: any[]) => void,
  calls: [] as any[],
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST', DELETE: 'DELETE' },
    makeCallToBackend: vi.fn((opts: any) => {
      h.calls.push(opts);
      const { path, httpMethod = 'GET', successCallback } = opts;
      if (path === '/m8flow/connectors-grouped') {
        successCallback(h.connectorsResponse);
      } else if (path.startsWith('/secrets?')) {
        const page =
          new URLSearchParams(path.split('?')[1]).get('page') ?? '1';
        successCallback(
          h.secretsPages[page] ?? { results: [], pagination: { pages: 1 } },
        );
      } else if (path.startsWith('/secrets')) {
        // create/update by key
        successCallback({});
      }
      // record-only for assertions on httpMethod
      void httpMethod;
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

vi.mock('react-i18next', () => {
  // Stable `t` reference: the component lists `t` in its data-loading effect
  // deps (matching real react-i18next, where `t` is stable). Returning a new
  // function each render would re-run the effect every render and re-set the
  // loading flag, leaving the form stuck on the spinner forever.
  const t = (key: string, opts?: { name?: string }) =>
    opts?.name ? `${key}:${opts.name}` : key;
  return {
    useTranslation: () => ({ t }),
  };
});

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => h.navigate,
    useParams: () => h.params,
  };
});

vi.mock('@casl/react', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../utils/connectorCardDisplay', () => ({
  ConnectorNameAvatar: () => <span data-testid="avatar" />,
}));

vi.mock('../components/Notification', () => ({
  Notification: ({ title }: { title?: string }) => (
    <div data-testid="notification">{title}</div>
  ),
}));

vi.mock('../helpers', () => ({
  setPageTitle: vi.fn(),
}));

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

const GITHUB_CONNECTOR = {
  id: 'github',
  name: 'GitHub',
  description: 'GitHub',
  status: 'available',
  icon: 'code',
  operationCount: 1,
  operations: [],
  configFields: [
    {
      id: 'pat_token',
      secretKey: 'GITHUB_PAT_TOKEN',
      label: 'Personal Access Token',
      type: 'password',
      required: true,
    },
  ],
};

const SMTP_CONNECTOR = {
  id: 'smtp',
  name: 'SMTP',
  description: 'SMTP',
  status: 'available',
  icon: 'email',
  operationCount: 1,
  operations: [],
  configFields: [
    {
      id: 'port',
      secretKey: 'SMTP_PORT',
      label: 'Port',
      type: 'text',
      required: true,
      format: 'port',
    },
  ],
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <ConnectorConfigure />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.connectorsResponse = [GITHUB_CONNECTOR];
  h.secretsPages = {};
  h.params = { connectorId: 'github' };
  h.navigate = vi.fn();
  h.calls = [];
});

describe('secretKeyFor', () => {
  it('uses the explicit secretKey verbatim', () => {
    expect(
      secretKeyFor('github', GITHUB_CONNECTOR.configFields[0] as any),
    ).toBe('GITHUB_PAT_TOKEN');
  });

  it('sanitizes a derived fallback key to word characters only', () => {
    expect(
      secretKeyFor('foo-bar', {
        id: 'baz-qux',
        label: 'x',
        type: 'text',
        required: true,
      } as any),
    ).toBe('foo_bar_baz_qux');
  });
});

describe('ConnectorConfigure existence detection', () => {
  it('detects a secret that lives beyond the first page and updates via PUT', async () => {
    // Two pages of secrets; the connector key only appears on page 2.
    h.secretsPages = {
      '1': { results: [{ key: 'UNRELATED' }], pagination: { pages: 2 } },
      '2': {
        results: [{ key: 'GITHUB_PAT_TOKEN' }],
        pagination: { pages: 2 },
      },
    };

    renderPage();

    // Field is recognized as already configured.
    expect(
      await screen.findByText('connector_config_field_set'),
    ).toBeInTheDocument();

    // Entering a new value and saving must UPDATE (PUT) the existing key,
    // not POST a duplicate.
    const input = screen
      .getByTestId('connector-config-field-pat_token')
      .querySelector('input')!;
    fireEvent.change(input, { target: { value: 'new-token' } });
    fireEvent.click(screen.getByTestId('connector-config-save'));

    await waitFor(() => {
      const putCall = h.calls.find(
        (c) => c.path === '/secrets/GITHUB_PAT_TOKEN',
      );
      expect(putCall).toBeTruthy();
      expect(putCall.httpMethod).toBe('PUT');
    });
    expect(
      h.calls.some((c) => c.path === '/secrets' && c.httpMethod === 'POST'),
    ).toBe(false);
  });

  it('shows a required error when a required field has no existing secret', async () => {
    h.secretsPages = {
      '1': { results: [], pagination: { pages: 1 } },
    };

    renderPage();

    // Not configured: wait for the form to render the field.
    await screen.findByTestId('connector-config-field-pat_token');
    expect(
      screen.queryByText('connector_config_field_set'),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('connector-config-save'));

    expect(
      await screen.findByText('connector_config_required_field'),
    ).toBeInTheDocument();
    // Nothing persisted.
    expect(h.calls.some((c) => c.path.startsWith('/secrets/'))).toBe(false);
  });
});

describe('ConnectorConfigure input validation', () => {
  beforeEach(() => {
    h.connectorsResponse = [SMTP_CONNECTOR];
    h.params = { connectorId: 'smtp' };
    h.secretsPages = { '1': { results: [], pagination: { pages: 1 } } };
  });

  it('shows a format error, disables Save, and blocks submission for an invalid port', async () => {
    renderPage();
    const input = (
      await screen.findByTestId('connector-config-field-port')
    ).querySelector('input')!;

    fireEvent.change(input, { target: { value: '0' } });

    expect(
      await screen.findByText('connector_config_invalid_port'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('connector-config-save')).toBeDisabled();

    // Even forcing a click persists nothing (the load-time GET aside, no write).
    fireEvent.click(screen.getByTestId('connector-config-save'));
    expect(
      h.calls.some(
        (c) =>
          (c.httpMethod === 'POST' || c.httpMethod === 'PUT') &&
          c.path.startsWith('/secrets'),
      ),
    ).toBe(false);
  });

  it('re-enables Save once the value is corrected and persists the trimmed value', async () => {
    renderPage();
    const input = (
      await screen.findByTestId('connector-config-field-port')
    ).querySelector('input')!;

    fireEvent.change(input, { target: { value: '0' } });
    expect(screen.getByTestId('connector-config-save')).toBeDisabled();

    // Correct it (with surrounding whitespace that must be trimmed away).
    fireEvent.change(input, { target: { value: '  587  ' } });
    await waitFor(() =>
      expect(screen.getByTestId('connector-config-save')).not.toBeDisabled(),
    );

    fireEvent.click(screen.getByTestId('connector-config-save'));

    await waitFor(() => {
      const post = h.calls.find(
        (c) => c.path === '/secrets' && c.httpMethod === 'POST',
      );
      expect(post).toBeTruthy();
      expect(post.postBody).toEqual({ key: 'SMTP_PORT', value: '587' });
    });
  });

  it('rejects a whitespace-only value', async () => {
    renderPage();
    const input = (
      await screen.findByTestId('connector-config-field-port')
    ).querySelector('input')!;

    fireEvent.change(input, { target: { value: '   ' } });

    expect(
      await screen.findByText('connector_config_whitespace_only'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('connector-config-save')).toBeDisabled();
  });
});
