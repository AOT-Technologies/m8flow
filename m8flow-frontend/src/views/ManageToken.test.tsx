import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ManageToken from './ManageToken';

type BackendCall = {
  path: string;
  httpMethod?: string;
  postBody?: any;
  successCallback: (result: any) => void;
  failureCallback?: (err: any) => void;
};

const h = vi.hoisted(() => ({
  canAccess: true,
  // Keys returned by the GET call.
  getResult: { keys: [] } as Record<string, any>,
  lastPostBody: null as any,
  lastDeletePath: null as string | null,
  clipboardWriteText: (() => Promise.resolve()) as (text: string) => Promise<void>,
  makeCallToBackend: (() => {}) as (args: BackendCall) => void,
  HttpMethods: { GET: 'GET', POST: 'POST', DELETE: 'DELETE' },
}));

vi.mock('../utils/useApi', () => ({
  useApi: () => ({
    makeCallToBackend: h.makeCallToBackend,
    HttpMethods: h.HttpMethods,
  }),
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => h.canAccess },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      m8flowNatsTokensPath: '/m8flow/nats-tokens',
    },
  })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../helpers', () => ({ setPageTitle: vi.fn() }));

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

const renderPage = () =>
  render(
    <MemoryRouter>
      <ManageToken />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.canAccess = true;
  h.getResult = { keys: [] };
  h.lastPostBody = null;
  h.lastDeletePath = null;
  h.clipboardWriteText = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: h.clipboardWriteText },
    configurable: true,
  });

  // Default backend behavior: GET lists keys, POST returns a fresh key,
  // DELETE reports revoked.
  h.makeCallToBackend = vi.fn((args: BackendCall) => {
    if (args.httpMethod === 'POST') {
      h.lastPostBody = args.postBody;
      args.successCallback({ token: 'm8f_abc.generated_secret', label: 'CI' });
    } else if (args.httpMethod === 'DELETE') {
      h.lastDeletePath = args.path;
      args.successCallback({ revoked: true, id: 'abc' });
    } else {
      args.successCallback(h.getResult);
    }
  });
});

describe('ManageToken', () => {
  it('shows the create form and an empty-state when no keys exist', async () => {
    renderPage();
    expect(
      await screen.findByTestId('manage-token-create-section'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('manage-token-label-input')).toBeInTheDocument();
    expect(screen.getByTestId('manage-token-expiry-select')).toBeInTheDocument();
    expect(screen.getByTestId('manage-token-create-button')).toBeInTheDocument();
    expect(await screen.findByTestId('manage-token-list-section')).toHaveTextContent(
      'manage_token_no_keys',
    );
  });

  it('requires a label before the create button is enabled', async () => {
    renderPage();
    const button = await screen.findByTestId('manage-token-create-button');
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByTestId('manage-token-label-input'), {
      target: { value: 'CI pipeline' },
    });
    expect(button).not.toBeDisabled();
  });

  it('creates a key and displays the value exactly once', async () => {
    renderPage();
    fireEvent.change(await screen.findByTestId('manage-token-label-input'), {
      target: { value: 'CI pipeline' },
    });
    fireEvent.click(screen.getByTestId('manage-token-create-button'));

    const tokenValue = await screen.findByTestId('manage-token-value');
    expect(tokenValue).toHaveTextContent('m8f_abc.generated_secret');
    // Label and default expiry (90 days) are sent; scope is omitted when empty.
    expect(h.lastPostBody).toEqual({
      label: 'CI pipeline',
      expiresInDays: 90,
    });

    // Dismissing re-fetches the list so the secret is no longer shown.
    fireEvent.click(screen.getByTestId('manage-token-done-button'));
    await waitFor(() =>
      expect(screen.queryByTestId('manage-token-value')).toBeNull(),
    );
  });

  it('sends a scope when one is provided', async () => {
    renderPage();
    fireEvent.change(await screen.findByTestId('manage-token-label-input'), {
      target: { value: 'Scoped' },
    });
    fireEvent.change(screen.getByTestId('manage-token-scope-input'), {
      target: { value: 'group-a/flow-a' },
    });
    fireEvent.click(screen.getByTestId('manage-token-create-button'));

    await screen.findByTestId('manage-token-value');
    expect(h.lastPostBody).toEqual({
      label: 'Scoped',
      expiresInDays: 90,
      scope: 'group-a/flow-a',
    });
  });

  it('copies the generated key to the clipboard', async () => {
    renderPage();
    fireEvent.change(await screen.findByTestId('manage-token-label-input'), {
      target: { value: 'CI' },
    });
    fireEvent.click(screen.getByTestId('manage-token-create-button'));
    fireEvent.click(await screen.findByTestId('manage-token-copy'));
    await waitFor(() =>
      expect(h.clipboardWriteText).toHaveBeenCalledWith('m8f_abc.generated_secret'),
    );
  });

  it('lists existing keys with a revoke action, without any value', async () => {
    h.getResult = {
      keys: [
        {
          id: 'abc',
          label: 'CI pipeline',
          createdAtInSeconds: 1_700_000_000,
          expiresAtInSeconds: null,
          lastUsedAtInSeconds: null,
          revokedAtInSeconds: null,
        },
      ],
    };
    renderPage();
    expect(await screen.findByTestId('manage-token-row-abc')).toBeInTheDocument();
    expect(screen.getByTestId('manage-token-revoke-abc')).toBeInTheDocument();
    expect(screen.queryByTestId('manage-token-value')).toBeNull();
  });

  it('requires confirmation before revoking a key and calls DELETE by id', async () => {
    h.getResult = {
      keys: [{ id: 'abc', label: 'CI pipeline', createdAtInSeconds: 1_700_000_000 }],
    };
    renderPage();
    fireEvent.click(await screen.findByTestId('manage-token-revoke-abc'));
    fireEvent.click(await screen.findByTestId('manage-token-revoke-confirm'));

    await waitFor(() =>
      expect(h.lastDeletePath).toEqual('/m8flow/nats-tokens/abc'),
    );
  });

  it('does not offer a revoke action for an already-revoked key', async () => {
    h.getResult = {
      keys: [
        {
          id: 'abc',
          label: 'CI pipeline',
          createdAtInSeconds: 1_700_000_000,
          revokedAtInSeconds: 1_700_000_500,
        },
      ],
    };
    renderPage();
    expect(await screen.findByTestId('manage-token-row-abc')).toBeInTheDocument();
    expect(screen.queryByTestId('manage-token-revoke-abc')).toBeNull();
  });

  it('redirects away when the user lacks permission', () => {
    h.canAccess = false;
    renderPage();
    expect(screen.queryByTestId('manage-token-page')).toBeNull();
  });
});
