import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SecretShow from './SecretShow';

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => true },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/UriListForPermissions', () => ({
  useUriListForPermissions: vi.fn(() => ({
    targetUris: {
      secretShowPath: '/secrets/api-key',
    },
  })),
}));

vi.mock('../contexts/Can', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../components/ProcessBreadcrumb', () => ({
  default: () => null,
}));

vi.mock('../components/ConfirmButton', () => ({
  default: () => null,
}));

vi.mock('../components/Notification', () => ({
  Notification: () => null,
}));

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => undefined,
  },
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useParams: () => ({ secret_identifier: 'api-key' }),
  };
});

import HttpService from '../services/HttpService';

describe('SecretShow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
      if (opts.path === '/secrets/api-key' && !opts.httpMethod) {
        opts.successCallback({ key: 'api-key', id: 1, value: '' });
      }
    });
  });

  it('loads /secrets/:id and PUTs only { value } on blind edit', () => {
    render(
      <MemoryRouter>
        <SecretShow />
      </MemoryRouter>,
    );

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/secrets/api-key' }),
    );
    const loadCall = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
    expect(loadCall.path).toBe('/secrets/api-key');
    expect(loadCall.path).not.toContain('show-value');
    expect(loadCall.httpMethod).toBeUndefined();

    fireEvent.click(screen.getByRole('button', { name: 'edit_secret_value' }));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'new-secret' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'update_value_button' }));

    const putCall = vi
      .mocked(HttpService.makeCallToBackend)
      .mock.calls.find((call) => call[0].httpMethod === 'PUT')?.[0];
    expect(putCall).toEqual(
      expect.objectContaining({
        path: '/secrets/api-key',
        httpMethod: 'PUT',
        postBody: { value: 'new-secret' },
      }),
    );
    expect(Object.keys(putCall?.postBody ?? {})).toEqual(['value']);
  });
});
