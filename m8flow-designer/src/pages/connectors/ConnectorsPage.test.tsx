import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({
    tenants: [],
    refreshTenants: () => {},
    organizationMemberships: [],
    activeTenantLabel: null,
  }),
}));
import type { ConnectorGroup } from '@/lib/api';
import ConnectorsPage from './ConnectorsPage';
import ConnectorProfilesPage from './ConnectorProfilesPage';
import ConnectorProfileEditPage, {
  connectorFieldError,
  slugifyIdentifier,
} from './ConnectorProfileEditPage';

const mockFetchConnectorsGrouped = vi.fn();
const mockFetchConnectorTemplate = vi.fn();
const mockFetchConnectorProfiles = vi.fn();
const mockFetchConnectorProfile = vi.fn();
const mockCreateConnectorProfile = vi.fn();
const mockUpdateConnectorProfile = vi.fn();
const mockDeactivateConnectorProfile = vi.fn();
const mockDeleteConnectorProfile = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    fetchConnectorsGrouped: (...args: unknown[]) => mockFetchConnectorsGrouped(...args),
  };
});

vi.mock('@/lib/connectorsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/connectorsApi')>(
    '@/lib/connectorsApi',
  );
  return {
    ...actual,
    fetchConnectorTemplate: (...args: unknown[]) => mockFetchConnectorTemplate(...args),
    fetchConnectorProfiles: (...args: unknown[]) => mockFetchConnectorProfiles(...args),
    fetchConnectorProfile: (...args: unknown[]) => mockFetchConnectorProfile(...args),
    createConnectorProfile: (...args: unknown[]) => mockCreateConnectorProfile(...args),
    updateConnectorProfile: (...args: unknown[]) => mockUpdateConnectorProfile(...args),
    deactivateConnectorProfile: (...args: unknown[]) => mockDeactivateConnectorProfile(...args),
    deleteConnectorProfile: (...args: unknown[]) => mockDeleteConnectorProfile(...args),
  };
});

const HTTP: ConnectorGroup = {
  id: 'http',
  name: 'HTTP',
  description: 'Make REST API calls from workflows',
  status: 'available',
  icon: 'globe',
  operationCount: 2,
  supportsProfiles: true,
  operations: [
    {
      id: 'http/GetRequestV2',
      name: 'GET',
      rawName: 'GetRequestV2',
      description: 'HTTP GET',
      parameters: [{ id: 'url', type: 'str' }],
    },
    {
      id: 'http/PostRequestV2',
      name: 'POST',
      rawName: 'PostRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'data', type: 'str' },
      ],
    },
  ],
};

const TEMPLATE = {
  id: 'http',
  name: 'HTTP',
  description: 'Make REST API calls from workflows',
  supportsProfiles: true,
  groups: [{ id: 'authentication', label: 'Authentication' }],
  profileFields: [
    {
      id: 'basic_auth_username',
      label: 'Basic Auth Username',
      type: 'text',
      required: false,
      secret: true,
      group: 'authentication',
    },
    {
      id: 'basic_auth_password',
      label: 'Basic Auth Password',
      type: 'password',
      required: false,
      secret: true,
      group: 'authentication',
    },
  ],
};

const PROFILE = {
  id: 7,
  connector_type: 'http',
  profile_name: 'http-prod',
  display_name: 'HTTP prod',
  description: null,
  config: {},
  configured_secrets: ['basic_auth_username', 'basic_auth_password'],
  is_active: true,
};

function renderAt(path: string, context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/connectors/:connectorId/profiles/new" element={<ConnectorProfileEditPage />} />
          <Route
            path="/connectors/:connectorId/profiles/:profileId/edit"
            element={<ConnectorProfileEditPage />}
          />
          <Route path="/connectors/:connectorId/profiles" element={<ConnectorProfilesPage />} />
          <Route path="/configuration/secrets" element={<p>secrets-page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const INTEGRATOR: SessionFixtureContext = {
  scopedTenantId: 't1',
  selectedTenantId: 't1',
  isSuperAdmin: false,
  canReadConnectors: true,
  canManageConnectorProfiles: true,
};

const EDITOR: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: null,
  isSuperAdmin: false,
  canReadConnectors: true,
  canManageConnectorProfiles: false,
};

describe('Connectors UI', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('explains denial when the role cannot read the catalog', () => {
    renderAt('/connectors', {
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canReadConnectors: false,
      canManageConnectorProfiles: false,
    });
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(mockFetchConnectorsGrouped).not.toHaveBeenCalled();
  });

  it('shows an empty catalog', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([]);
    renderAt('/connectors', INTEGRATOR);
    expect(await screen.findByTestId('connectors-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('connectors-search')).not.toBeInTheDocument();
  });

  it('lists HTTP, searches, and opens operations', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([HTTP]);
    renderAt('/connectors', EDITOR);

    expect(await screen.findByTestId('connector-name-http')).toHaveTextContent('HTTP');
    expect(screen.getByTestId('connector-op-count-http')).toHaveTextContent('2 operations');
    expect(screen.getByTestId('connector-configure-http')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('connectors-search'), { target: { value: 'smtp' } });
    expect(screen.getByTestId('connectors-no-match')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('connectors-search'), { target: { value: 'GetRequest' } });
    expect(screen.getByTestId('connector-card-http')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('connector-view-ops-http'));
    expect(await screen.findByRole('dialog', { name: 'HTTP operations' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-operation-http/GetRequestV2')).toHaveTextContent('url');
  });

  it('sends HTTP Configure to profiles, not Configuration secrets', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([HTTP]);
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors', EDITOR);

    fireEvent.click(await screen.findByTestId('connector-configure-http'));
    expect(await screen.findByTestId('connector-profiles-empty')).toBeInTheDocument();
    expect(screen.queryByText('secrets-page')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add profile/i })).not.toBeInTheDocument();
  });

  it('sends Configure to Configuration secrets when the family has no profiles', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([
      { ...HTTP, id: 'smtp', name: 'SMTP', supportsProfiles: false, operationCount: 1, operations: [] },
    ]);
    renderAt('/connectors', INTEGRATOR);

    fireEvent.click(await screen.findByTestId('connector-configure-smtp'));
    expect(await screen.findByText('secrets-page')).toBeInTheDocument();
  });

  it('lists profiles across tenants for an All-Tenants super-admin', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles', {
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: true,
      canReadConnectors: true,
      canManageConnectorProfiles: true,
    });

    expect(await screen.findByText('HTTP prod')).toBeInTheDocument();
    expect(screen.queryByText('Choose a tenant')).not.toBeInTheDocument();
    // Profile writes must target one tenant, so the write chrome stays hidden.
    expect(screen.queryByRole('button', { name: /New profile/i })).not.toBeInTheDocument();
  });

  it('lets an editor list profiles without write chrome', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles', EDITOR);

    expect(await screen.findByText('HTTP prod')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connectors' })).toBeInTheDocument();
    expect(screen.getByText('http-prod')).toBeInTheDocument();
    expect(screen.getByText('basic_auth_username, basic_auth_password')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add profile/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(mockFetchConnectorProfiles).toHaveBeenCalledWith({
      connectorType: 'http',
      tenantId: null,
    });
  });

  it('lets an integrator create, edit, deactivate, and delete', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    mockDeactivateConnectorProfile.mockResolvedValue(undefined);
    renderAt('/connectors/http/profiles', INTEGRATOR);

    expect(await screen.findByRole('link', { name: /Add profile/i })).toHaveAttribute(
      'href',
      '/connectors/http/profiles/new',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => {
      expect(mockDeactivateConnectorProfile).toHaveBeenCalledWith(7, 't1');
    });
  });

  it('blocks an editor from the create form', () => {
    renderAt('/connectors/http/profiles/new', EDITOR);
    expect(screen.getByText('Not allowed')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Connector profiles' })).toBeInTheDocument();
    expect(mockCreateConnectorProfile).not.toHaveBeenCalled();
    expect(mockFetchConnectorTemplate).not.toHaveBeenCalled();
  });

  it('creates a profile and never redisplays the password', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockCreateConnectorProfile.mockResolvedValue({
      ...PROFILE,
      profile_name: 'http-staging',
      display_name: 'HTTP staging',
      configured_secrets: ['basic_auth_password'],
    });
    mockFetchConnectorProfiles.mockResolvedValueOnce([]).mockResolvedValue([
      {
        ...PROFILE,
        profile_name: 'http-staging',
        display_name: 'HTTP staging',
        configured_secrets: ['basic_auth_password'],
      },
    ]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    expect(await screen.findByRole('heading', { name: 'Add HTTP profile' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'HTTP profiles' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Connectors' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-name')).toHaveAttribute('readonly');
    fireEvent.change(screen.getByTestId('connector-profile-display-name'), {
      target: { value: 'HTTP staging' },
    });
    expect(screen.getByTestId('connector-profile-name')).toHaveValue('http-staging');
    fireEvent.change(screen.getByTestId('connector-profile-field-basic_auth_password'), {
      target: { value: 'super-secret' },
    });
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockCreateConnectorProfile).toHaveBeenCalledWith(
        {
          connector_type: 'http',
          profile_name: 'http-staging',
          display_name: 'HTTP staging',
          description: null,
          config: { basic_auth_password: 'super-secret' },
        },
        't1',
      );
    });
    expect(await screen.findByText('HTTP staging')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('super-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('super-secret')).not.toBeInTheDocument();
  });

  it('sends only typed secrets on edit so a blank password is left unchanged', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    expect(await screen.findByRole('heading', { name: 'Edit HTTP profile' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-name')).toHaveValue('http-prod');
    expect(screen.getByTestId('connector-profile-name')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-field-basic_auth_password')).toHaveValue('');
    fireEvent.change(screen.getByTestId('connector-profile-display-name'), {
      target: { value: 'HTTP production' },
    });
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        {
          display_name: 'HTTP production',
          description: null,
          config: {},
        },
        't1',
      );
    });
  });

  it('blocks a duplicate identifier before calling the API', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'HTTP Prod' },
    });
    expect(screen.getByText(/identifier "http-prod" already exists/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('connector-profile-save'));
    expect(await screen.findByText('Fix the highlighted fields and try again.')).toBeInTheDocument();
    expect(mockCreateConnectorProfile).not.toHaveBeenCalled();
  });

  it('requires a display name and masks only the password', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    const password = await screen.findByTestId('connector-profile-field-basic_auth_password');
    expect(password).toHaveAttribute('type', 'password');
    expect(screen.getByTestId('connector-profile-field-basic_auth_username')).toHaveAttribute(
      'type',
      'text',
    );
    expect(screen.queryByRole('button', { name: /basic auth username/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show basic auth password' }));
    expect(password).toHaveAttribute('type', 'text');

    fireEvent.click(screen.getByTestId('connector-profile-save'));
    expect(await screen.findByText('Display name is required.')).toBeInTheDocument();
    expect(mockCreateConnectorProfile).not.toHaveBeenCalled();
  });

  it('confirms before leaving a form with unsaved changes', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'Draft' },
    });
    fireEvent.click(screen.getByRole('link', { name: 'Cancel' }));
    expect(await screen.findByText('Discard unsaved changes?')).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-display-name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(await screen.findByTestId('connector-profiles-empty')).toBeInTheDocument();
  });

  it('does not confirm on a same-page hash link', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'Draft' },
    });
    const hashLink = document.createElement('a');
    hashLink.href = '#section';
    document.body.append(hashLink);
    fireEvent.click(hashLink);
    hashLink.remove();
    expect(screen.queryByText('Discard unsaved changes?')).not.toBeInTheDocument();
  });
});

describe('connector profile form helpers', () => {
  it('slugifies display names into identifiers', () => {
    expect(slugifyIdentifier('  Slack – Prod!! ')).toBe('slack-prod');
    expect(slugifyIdentifier('Café Ops 2')).toBe('cafe-ops-2');
    expect(slugifyIdentifier('!!!')).toBe('');
    expect(slugifyIdentifier('a'.repeat(70))).toHaveLength(64);
  });

  it('validates required, url, port and pattern fields', () => {
    const base = { id: 'x', label: 'Instance URL', required: true };
    expect(connectorFieldError({ ...base, type: 'url' }, '', false)).toBe('Instance URL is required.');
    expect(connectorFieldError({ ...base, type: 'url' }, '', true)).toBeNull();
    expect(connectorFieldError({ ...base, type: 'url' }, 'example.com', false)).toMatch(/full URL/);
    expect(connectorFieldError({ ...base, type: 'url' }, 'https://a.my.salesforce.com', false)).toBeNull();
    expect(connectorFieldError({ ...base, type: 'port' }, '70000', false)).toMatch(/between 1 and 65535/);
    expect(connectorFieldError({ ...base, type: 'port' }, '587', false)).toBeNull();
    const stripe = {
      id: 'api_key',
      label: 'Secret key',
      type: 'password',
      required: true,
      pattern: '^(sk|rk)_(test|live)_[A-Za-z0-9]+$',
      patternMessage: 'bad key',
    };
    expect(connectorFieldError(stripe, 'pk_test_abc', false)).toBe('bad key');
    expect(connectorFieldError(stripe, 'sk_live_abc123', false)).toBeNull();
  });

  it('treats a malformed pattern as no pattern and warns', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const field = { id: 'x', label: 'Key', type: 'text', required: true, pattern: '(' };
    expect(connectorFieldError(field, 'anything', false)).toBeNull();
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('"x"'));
    warn.mockRestore();
  });
});
