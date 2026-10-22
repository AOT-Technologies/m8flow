import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom';
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
  DISPLAY_NAME_HINT,
  displayNameError,
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
      example: 'svc-account',
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
  updated_at: '2026-10-14T10:00:00+00:00',
};

/** The single-profile read an integrator gets: plain settings, no credentials. */
const PROFILE_DETAIL = { ...PROFILE, config: { basic_auth_username: 'api-user' } };

/** Data router (as in App) so the profile form's useBlocker works; `path` may
 * be a history stack, the last entry being the current page. */
function renderAt(path: string | string[], context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  const entries = Array.isArray(path) ? path : [path];
  const router = createMemoryRouter(
    [
      {
        element: <Outlet context={context} />,
        children: [
          { path: '/connectors', element: <ConnectorsPage /> },
          { path: '/connectors/:connectorId/profiles/new', element: <ConnectorProfileEditPage /> },
          { path: '/connectors/:connectorId/profiles/:profileId/edit', element: <ConnectorProfileEditPage /> },
          { path: '/connectors/:connectorId/profiles', element: <ConnectorProfilesPage /> },
          { path: '/configuration/secrets', element: <p>secrets-page</p> },
        ],
      },
    ],
    { initialEntries: entries, initialIndex: entries.length - 1 },
  );
  render(<RouterProvider router={router} />);
  return router;
}

const INTEGRATOR: SessionFixtureContext = {
  scopedTenantId: 't1',
  selectedTenantId: 't1',
  isSuperAdmin: false,
  canReadConnectors: true,
  canManageConnectorProfiles: true,
  canManageSecrets: true,
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
    expect(screen.queryByTestId('connector-configure-http')).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId('connectors-search'), { target: { value: 'smtp' } });
    expect(screen.getByTestId('connectors-no-match')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('connectors-search'), { target: { value: 'GetRequest' } });
    expect(screen.getByTestId('connector-card-http')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('connector-view-ops-http'));
    expect(await screen.findByRole('dialog', { name: 'HTTP operations' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-operation-http/GetRequestV2')).toHaveTextContent('url');
  });

  it('keeps HTTP profile configuration available to users with write permission', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([HTTP]);
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors', INTEGRATOR);

    fireEvent.click(await screen.findByTestId('connector-configure-http'));
    expect(await screen.findByTestId('connector-profiles-empty')).toHaveTextContent(
      'No profiles yet. Add one to select it from a Service Task.',
    );
    expect(screen.queryByText('secrets-page')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add profile/i })).toBeInTheDocument();
  });

  it('sends Configure to Configuration secrets when the family has no profiles', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([
      { ...HTTP, id: 'smtp', name: 'SMTP', supportsProfiles: false, operationCount: 1, operations: [] },
    ]);
    renderAt('/connectors', INTEGRATOR);

    fireEvent.click(await screen.findByTestId('connector-configure-smtp'));
    expect(await screen.findByText('secrets-page')).toBeInTheDocument();
  });

  it('hides Configure for connectors backed by secrets when the user cannot write secrets', async () => {
    mockFetchConnectorsGrouped.mockResolvedValue([
      { ...HTTP, id: 'smtp', name: 'SMTP', supportsProfiles: false, operationCount: 1, operations: [] },
    ]);
    renderAt('/connectors', EDITOR);

    expect(await screen.findByTestId('connector-name-smtp')).toBeInTheDocument();
    expect(screen.queryByTestId('connector-configure-smtp')).not.toBeInTheDocument();
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

  it('tells an All-Tenants super-admin to pick a tenant when no profiles exist', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors/http/profiles', {
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: true,
      canReadConnectors: true,
      canManageConnectorProfiles: true,
    });

    expect(await screen.findByTestId('connector-profiles-empty')).toHaveTextContent(
      'No profiles yet. Select a tenant to add one.',
    );
  });

  it('lets an editor list profiles without write chrome', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles', EDITOR);

    expect(await screen.findByText('HTTP prod')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connectors' })).toBeInTheDocument();
    expect(screen.getByText('http-prod')).toBeInTheDocument();
    expect(screen.getByText('Configured')).toBeInTheDocument();
    expect(screen.getByText('Last updated')).toBeInTheDocument();
    expect(screen.getByTitle(new Date(PROFILE.updated_at).toLocaleString())).toHaveTextContent(/ago|just now/);
    expect(screen.queryByText(/basic_auth_username/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add profile/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(mockFetchConnectorProfiles).toHaveBeenCalledWith({
      connectorType: 'http',
      tenantId: null,
    });
  });

  it('falls back to no tooltip for a malformed updated_at instead of "Invalid Date"', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([{ ...PROFILE, updated_at: 'not-a-date' }]);
    renderAt('/connectors/http/profiles', EDITOR);

    const cell = await screen.findByText('—');
    expect(cell).not.toHaveAttribute('title');
  });

  it('marks a profile missing a required value as incomplete', async () => {
    mockFetchConnectorTemplate.mockResolvedValue({
      ...TEMPLATE,
      profileFields: TEMPLATE.profileFields.map((field) => ({ ...field, required: true })),
    });
    mockFetchConnectorProfiles.mockResolvedValue([
      { ...PROFILE, configured_secrets: ['basic_auth_username'], updated_at: null },
    ]);
    renderAt('/connectors/http/profiles', EDITOR);

    expect(await screen.findByText('Incomplete')).toBeInTheDocument();
    expect(screen.getByText('Missing: Basic Auth Password')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
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

  it('prefills saved settings, hides saved credentials, and sends only changes', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    expect(await screen.findByRole('heading', { name: 'Edit HTTP profile' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-name')).toHaveValue('http-prod');
    expect(screen.getByTestId('connector-profile-name')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-field-basic_auth_username')).toHaveValue('api-user');
    // A saved credential shows its status, not an input or dots.
    expect(screen.queryByTestId('connector-profile-field-basic_auth_password')).not.toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-input-basic_auth_password-status')).toHaveTextContent(
      'Configured',
    );
    expect(screen.getByRole('button', { name: 'Replace basic auth password' })).toBeInTheDocument();
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

  it('replaces a saved credential and clears an optional value', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.click(await screen.findByRole('button', { name: 'Replace basic auth password' }));
    const password = screen.getByTestId('connector-profile-field-basic_auth_password');
    expect(password).toHaveValue('');
    expect(password).toHaveAttribute('placeholder', 'Enter a new value');
    expect(screen.getByText(/Leave blank to keep the saved value/)).toBeInTheDocument();
    fireEvent.change(password, { target: { value: 'new-secret' } });

    fireEvent.click(screen.getByRole('button', { name: 'Clear basic auth username' }));
    expect(screen.queryByTestId('connector-profile-field-basic_auth_username')).not.toBeInTheDocument();
    expect(screen.getByTestId('connector-profile-input-basic_auth_username-status')).toHaveTextContent(
      'Will be cleared',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Undo basic auth username' }));
    expect(screen.getByTestId('connector-profile-field-basic_auth_username')).toHaveValue('api-user');
    fireEvent.click(screen.getByRole('button', { name: 'Clear basic auth username' }));
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        {
          display_name: 'HTTP prod',
          description: null,
          config: { basic_auth_password: 'new-secret' },
          clear: ['basic_auth_username'],
        },
        't1',
      );
    });
  });

  it('keeps a prefilled optional value the user blanks out', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-field-basic_auth_username'), {
      target: { value: '' },
    });
    // Only the Clear button removes a value; an emptied input keeps it.
    expect(screen.getByTestId('connector-profile-input-basic_auth_username-status')).toHaveTextContent(
      'Configured',
    );
    expect(screen.getByText(/Leave blank to keep the saved value/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        { display_name: 'HTTP prod', description: null, config: {} },
        't1',
      );
    });
  });

  it('sends a cleared field once even when its saved value is blank', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue({ ...PROFILE_DETAIL, config: { basic_auth_username: '' } });
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.click(await screen.findByRole('button', { name: 'Clear basic auth username' }));
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        { display_name: 'HTTP prod', description: null, config: {}, clear: ['basic_auth_username'] },
        't1',
      );
    });
  });

  it('does not carry a pending clear over to another profile', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    const router = renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.click(await screen.findByRole('button', { name: 'Clear basic auth username' }));
    await act(() => router.navigate('/connectors/http/profiles/8/edit'));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));

    expect(await screen.findByTestId('connector-profile-field-basic_auth_username')).toHaveValue('api-user');
    expect(screen.getByTestId('connector-profile-input-basic_auth_username-status')).toHaveTextContent(
      'Configured',
    );
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        8,
        { display_name: 'HTTP prod', description: null, config: {} },
        't1',
      );
    });
  });

  it('keeps a prefilled required value the user blanks out', async () => {
    mockFetchConnectorTemplate.mockResolvedValue({
      ...TEMPLATE,
      profileFields: TEMPLATE.profileFields.map((field) =>
        field.id === 'basic_auth_username' ? { ...field, required: true } : field,
      ),
    });
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockUpdateConnectorProfile.mockResolvedValue(PROFILE);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-field-basic_auth_username'), {
      target: { value: '  ' },
    });
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        { display_name: 'HTTP prod', description: null, config: {} },
        't1',
      );
    });
    expect(screen.queryByText('Basic Auth Username is required.')).not.toBeInTheDocument();
  });

  it('cancelling Replace leaves the saved credential untouched', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(PROFILE_DETAIL);
    mockFetchConnectorProfiles.mockResolvedValue([PROFILE]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    fireEvent.click(await screen.findByRole('button', { name: 'Replace basic auth password' }));
    fireEvent.change(screen.getByTestId('connector-profile-field-basic_auth_password'), {
      target: { value: 'typo' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel basic auth password' }));
    expect(screen.queryByTestId('connector-profile-field-basic_auth_password')).not.toBeInTheDocument();
    // Back to the loaded state, so leaving does not prompt.
    fireEvent.click(screen.getByRole('link', { name: 'Cancel' }));
    expect(await screen.findByText('HTTP prod')).toBeInTheDocument();
    expect(screen.queryByText('Discard unsaved changes?')).not.toBeInTheDocument();
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

  it('rejects a special-character display name inline and shows the rules', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    const name = await screen.findByTestId('connector-profile-display-name');
    expect(screen.getByText(`3-60 characters. ${DISPLAY_NAME_HINT}`)).toBeInTheDocument();
    fireEvent.change(name, { target: { value: '@#%$%%a$#%^&**gf' } });
    fireEvent.click(screen.getByTestId('connector-profile-save'));
    expect(await screen.findByText(DISPLAY_NAME_HINT, { selector: '[role="alert"]' })).toBeInTheDocument();
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(mockCreateConnectorProfile).not.toHaveBeenCalled();
  });

  it('saves a valid name with parentheses and flags a too-short identifier', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    mockCreateConnectorProfile.mockResolvedValue(PROFILE);
    renderAt('/connectors/http/profiles/new', INTEGRATOR);

    const name = await screen.findByTestId('connector-profile-display-name');
    fireEvent.change(name, { target: { value: 'ab.' } });
    expect(screen.getByText(/only the Latin letters and digits/)).toBeInTheDocument();
    // A valid non-Latin name yields no identifier; the error says why.
    fireEvent.change(name, { target: { value: '日本語コネクタ' } });
    expect(screen.getByText(/only the Latin letters and digits/)).toBeInTheDocument();
    fireEvent.change(name, { target: { value: 'GitHub Prod (Org A)' } });
    expect(screen.queryByText(/only the Latin letters and digits/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      expect(mockCreateConnectorProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          profile_name: 'github-prod-org-a',
          display_name: 'GitHub Prod (Org A)',
        }),
        't1',
      );
    });
  });

  it('keeps a legacy display name saveable but recommends a rename', async () => {
    const legacy = { ...PROFILE_DETAIL, display_name: '@@legacy' };
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfile.mockResolvedValue(legacy);
    mockUpdateConnectorProfile.mockResolvedValue(legacy);
    mockFetchConnectorProfiles.mockResolvedValue([legacy]);
    renderAt('/connectors/http/profiles/7/edit', INTEGRATOR);

    expect(await screen.findByTestId('connector-profile-legacy-name')).toHaveTextContent(
      /doesn't meet the current naming rules/,
    );
    fireEvent.click(screen.getByTestId('connector-profile-save'));
    await waitFor(() => {
      expect(mockUpdateConnectorProfile).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ display_name: '@@legacy' }),
        't1',
      );
    });
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
    expect(screen.getByTestId('connector-profile-field-basic_auth_username')).toHaveAttribute(
      'placeholder',
      'e.g. svc-account',
    );
    // A new profile has nothing saved, so there is no field status yet.
    expect(screen.queryByText('Not set')).not.toBeInTheDocument();
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
    expect(await screen.findByTestId('connector-profiles-empty')).toHaveTextContent(
      'No profiles yet. Add one to select it from a Service Task.',
    );
  });

  it('does not confirm on a same-page hash change', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    const router = renderAt('/connectors/http/profiles/new', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'Draft' },
    });
    await act(() => router.navigate('/connectors/http/profiles/new#section'));
    expect(router.state.location.hash).toBe('#section');
    expect(screen.queryByText('Discard unsaved changes?')).not.toBeInTheDocument();
  });

  it('confirms when programmatic navigation changes the query, even with a hash', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    const router = renderAt('/connectors/http/profiles/new', INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'Draft' },
    });
    await act(() => router.navigate('/connectors/http/profiles/new?copy=1#section'));
    expect(await screen.findByText('Discard unsaved changes?')).toBeInTheDocument();
    expect(router.state.location.search).toBe('');
  });

  it('confirms before browser Back leaves a form with unsaved changes', async () => {
    mockFetchConnectorTemplate.mockResolvedValue(TEMPLATE);
    mockFetchConnectorProfiles.mockResolvedValue([]);
    const router = renderAt(['/connectors/http/profiles', '/connectors/http/profiles/new'], INTEGRATOR);

    fireEvent.change(await screen.findByTestId('connector-profile-display-name'), {
      target: { value: 'Draft' },
    });

    await act(() => router.navigate(-1));
    expect(await screen.findByText('Discard unsaved changes?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    await waitFor(() => expect(screen.queryByText('Discard unsaved changes?')).not.toBeInTheDocument());
    expect(router.state.location.pathname).toBe('/connectors/http/profiles/new');
    expect(screen.getByTestId('connector-profile-display-name')).toHaveValue('Draft');

    await act(() => router.navigate(-1));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));
    expect(await screen.findByTestId('connector-profiles-empty')).toBeInTheDocument();
  });
});

describe('connector profile form helpers', () => {
  it('slugifies display names into identifiers', () => {
    expect(slugifyIdentifier('  Slack – Prod!! ')).toBe('slack-prod');
    expect(slugifyIdentifier('Café Ops 2')).toBe('cafe-ops-2');
    expect(slugifyIdentifier('!!!')).toBe('');
    expect(slugifyIdentifier('a'.repeat(70))).toHaveLength(50);
  });

  it('validates display names', () => {
    expect(displayNameError('  ')).toBe('Display name is required.');
    expect(displayNameError('ab')).toMatch(/3-60 characters/);
    expect(displayNameError('x'.repeat(61))).toMatch(/3-60 characters/);
    expect(displayNameError('!!!')).toBe(DISPLAY_NAME_HINT);
    expect(displayNameError('@#%$%%a$#%^&**gf')).toBe(DISPLAY_NAME_HINT);
    expect(displayNameError('Prod/HTTP')).toBe(DISPLAY_NAME_HINT);
    expect(displayNameError(' GitHub Prod (Org A) ')).toBeNull();
    expect(displayNameError('Café ops_2.v1-x')).toBeNull();
    // Counted in code points, like the backend's len(): 𝐀 is one letter.
    expect(displayNameError('𝐀𝐁')).toMatch(/3-60 characters/);
    expect(displayNameError('𝐀𝐁𝐂')).toBeNull();
    // Same cases as test_display_name_unicode_rules_match_the_designer in
    // m8flow-backend test_connector_profiles.py; keep in sync.
    expect(displayNameError('Ⅷ ops')).toBeNull(); // Ⅷ, letter-number (Nl)
    expect(displayNameError('x² ops')).toBeNull(); // superscript two (No)
    expect(displayNameError('〇 ops')).toBeNull(); // 〇, ideographic zero (Nl)
    expect(displayNameError('́abc')).toBe(DISPLAY_NAME_HINT); // leading combining mark
    expect(displayNameError('_abc')).toBe(DISPLAY_NAME_HINT);
    expect(displayNameError('Café ops')).toBe(DISPLAY_NAME_HINT); // NFD accent
  });

  it('validates required, url, port and pattern fields', () => {
    const base = { id: 'x', label: 'Instance URL', required: true };
    expect(connectorFieldError({ ...base, type: 'url' }, '', false)).toBe('Instance URL is required.');
    expect(connectorFieldError({ ...base, type: 'url' }, '', true)).toBeNull();
    expect(connectorFieldError({ ...base, type: 'url' }, 'example.com', false)).toBe(
      'Enter a full URL starting with http:// or https://.',
    );
    expect(connectorFieldError({ ...base, type: 'url' }, 'ftp://example.com', false)).toMatch(/full URL/);
    expect(connectorFieldError({ ...base, type: 'url' }, 'http://intranet:8080', false)).toBeNull();
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
