import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import ConnectorConfigure from './ConnectorConfigure';

// Shared, mutable state the hoisted mocks read from.
const h = vi.hoisted(() => ({
  template: null as any,
  profiles: [] as any[],
  params: { connectorId: 'smtp' } as Record<string, string>,
  navigate: (() => {}) as (...args: any[]) => void,
  calls: [] as any[],
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST', PUT: 'PUT', DELETE: 'DELETE' },
    makeCallToBackend: vi.fn((opts: any) => {
      h.calls.push(opts);
      const { path, httpMethod = 'GET', successCallback } = opts;
      if (path.startsWith('/m8flow/connector-templates/')) {
        successCallback(h.template);
      } else if (path.startsWith('/m8flow/connector-profiles') && httpMethod === 'GET') {
        successCallback(h.profiles);
      } else {
        successCallback({});
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
      connectorProfilesPath: '/m8flow/connector-profiles',
    },
  })),
}));

vi.mock('react-i18next', () => {
  // Stable `t` reference: the component lists `t` in its data-loading effect
  // deps (matching real react-i18next, where `t` is stable). A new function per
  // render would re-run the effect and leave the page stuck on the spinner.
  const t = (key: string, opts?: { name?: string }) =>
    opts?.name ? `${key}:${opts.name}` : key;
  return { useTranslation: () => ({ t }) };
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

const SMTP_TEMPLATE = {
  id: 'smtp',
  name: 'SMTP',
  description: 'Send emails through SMTP',
  supportsProfiles: true,
  groups: [],
  profileFields: [
    { id: 'smtp_host', label: 'Host', type: 'text', required: true, secret: false },
    { id: 'smtp_password', label: 'Password', type: 'password', required: false, secret: true },
  ],
};

const STAGING = {
  id: 7,
  connector_type: 'smtp',
  profile_name: 'smtp-staging',
  display_name: 'SMTP Staging',
  description: null,
  config: { smtp_host: 'smtp.staging.example.com' },
  configured_secrets: ['smtp_password'],
  is_active: true,
  is_default: false,
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <ConnectorConfigure />
    </MemoryRouter>,
  );

const valueOf = (testId: string) =>
  (screen.getByTestId(testId).querySelector('input') as HTMLInputElement).value;

const typeInto = (testId: string, value: string) => {
  const input = screen.getByTestId(testId).querySelector('input')!;
  fireEvent.change(input, { target: { value } });
};

beforeEach(() => {
  h.template = SMTP_TEMPLATE;
  h.profiles = [STAGING];
  h.params = { connectorId: 'smtp' };
  h.navigate = vi.fn();
  h.calls = [];
});

describe('ConnectorConfigure profile list', () => {
  it('lists the tenant profiles for this connector', async () => {
    renderPage();
    expect(
      await screen.findByTestId('connector-profile-row-smtp-staging'),
    ).toBeInTheDocument();
  });

  it('asks the backend only for this connector profiles', async () => {
    renderPage();
    await screen.findByTestId('connector-profile-row-smtp-staging');
    expect(
      h.calls.some((c) => c.path === '/m8flow/connector-profiles?connector_type=smtp'),
    ).toBe(true);
  });

  it('redirects connectors that have no profile fields', async () => {
    h.template = { ...SMTP_TEMPLATE, supportsProfiles: false, profileFields: [] };
    renderPage();
    await waitFor(() => expect(screen.queryByTestId('connector-profiles-page')).toBeNull());
  });
});

describe('ConnectorConfigure create', () => {
  it('requires a profile name', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('connector-profile-add'));
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    expect(
      await screen.findByText('connector_profile_name_required'),
    ).toBeInTheDocument();
    expect(h.calls.some((c) => c.httpMethod === 'POST')).toBe(false);
  });

  it('validates a required field before posting', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('connector-profile-add'));
    typeInto('connector-profile-identifier-input', 'smtp-production');
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    expect(
      await screen.findByText('connector_config_required_field'),
    ).toBeInTheDocument();
    expect(h.calls.some((c) => c.httpMethod === 'POST')).toBe(false);
  });

  it('posts the trimmed values', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('connector-profile-add'));
    typeInto('connector-profile-identifier-input', 'smtp-production');
    typeInto('connector-profile-field-smtp_host', '  smtp.example.com  ');
    typeInto('connector-profile-field-smtp_password', 'hunter2');
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      const post = h.calls.find(
        (c) => c.path === '/m8flow/connector-profiles' && c.httpMethod === 'POST',
      );
      expect(post).toBeTruthy();
      expect(post.postBody).toEqual({
        connector_type: 'smtp',
        profile_name: 'smtp-production',
        display_name: 'smtp-production',
        config: { smtp_host: 'smtp.example.com', smtp_password: 'hunter2' },
      });
    });
  });
});

describe('ConnectorConfigure edit', () => {
  it('prefills config values but never a stored secret', async () => {
    renderPage();
    await screen.findByTestId('connector-profile-row-smtp-staging');
    fireEvent.click(screen.getByTestId('connector-profile-edit-smtp-staging'));

    await waitFor(() =>
      expect(valueOf('connector-profile-field-smtp_host')).toBe(
        'smtp.staging.example.com',
      ),
    );
    expect(valueOf('connector-profile-field-smtp_password')).toBe('');
    expect(screen.getByText('connector_config_field_set')).toBeInTheDocument();
  });

  it('omits an untouched secret from the update so the stored value survives', async () => {
    renderPage();
    await screen.findByTestId('connector-profile-row-smtp-staging');
    fireEvent.click(screen.getByTestId('connector-profile-edit-smtp-staging'));
    await screen.findByTestId('connector-profile-field-smtp_host');

    typeInto('connector-profile-field-smtp_host', 'smtp.new.example.com');
    fireEvent.click(screen.getByTestId('connector-profile-save'));

    await waitFor(() => {
      const update = h.calls.find(
        (c) => c.path === '/m8flow/connector-profiles/7' && c.httpMethod === 'PUT',
      );
      expect(update).toBeTruthy();
      expect(update.postBody.config).toEqual({ smtp_host: 'smtp.new.example.com' });
      expect('smtp_password' in update.postBody.config).toBe(false);
    });
  });
});
