import { afterEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.fn();

vi.mock('./api', () => ({
  apiGet: (...args: unknown[]) => mockApiGet(...args),
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(path: string, status: number) {
      super(`${path} ${status}`);
      this.status = status;
    }
  },
}));

import {
  PROFILE_NAME_RE,
  connectorProfileItemPath,
  connectorProfilesPath,
  connectorTemplatePath,
  fetchConnectorProfilesForPicker,
} from './connectorsApi';

describe('connectorsApi paths', () => {
  it('encodes the template type', () => {
    expect(connectorTemplatePath('http')).toBe('/v1.0/m8flow/connector-templates/http');
  });

  it('lists with connector_type and tenant, and omits include_inactive unless false', () => {
    expect(connectorProfilesPath({ connectorType: 'http', tenantId: 't1' })).toBe(
      '/v1.0/m8flow/connector-profiles?tenantId=t1&connector_type=http',
    );
    expect(
      connectorProfilesPath({
        connectorType: 'http',
        includeInactive: false,
        tenantId: 't1',
      }),
    ).toBe(
      '/v1.0/m8flow/connector-profiles?tenantId=t1&connector_type=http&include_inactive=false',
    );
  });

  it('hard-deletes with hard=true', () => {
    expect(connectorProfileItemPath(7, 't1', { hard: 'true' })).toBe(
      '/v1.0/m8flow/connector-profiles/7?tenantId=t1&hard=true',
    );
  });

  it('accepts the host profile-name alphabet', () => {
    expect(PROFILE_NAME_RE.test('http-prod')).toBe(true);
    expect(PROFILE_NAME_RE.test('a')).toBe(true);
    expect(PROFILE_NAME_RE.test('-bad')).toBe(false);
  });
});

describe('fetchConnectorProfilesForPicker', () => {
  afterEach(() => {
    mockApiGet.mockReset();
  });

  it('loads active HTTP profiles and the template field ids to hide', async () => {
    mockApiGet.mockImplementation(async (path: string) => {
      if (path.includes('connector-templates/http')) {
        return {
          id: 'http',
          name: 'HTTP',
          description: '',
          supportsProfiles: true,
          profileFields: [
            { id: 'basic_auth_username', label: 'Basic Auth Username' },
            { id: 'basic_auth_password', label: 'Basic Auth Password' },
          ],
        };
      }
      if (path.includes('connector-profiles')) {
        expect(path).toContain('include_inactive=false');
        expect(path).toContain('connector_type=http');
        return [
          {
            id: 1,
            connector_type: 'http',
            profile_name: 'http-prod',
            display_name: 'HTTP prod',
            description: null,
            config: {},
            configured_secrets: ['basic_auth_password'],
            is_active: true,
          },
        ];
      }
      throw new Error(path);
    });

    await expect(fetchConnectorProfilesForPicker('http', 't1')).resolves.toEqual({
      profiles: [{ profile_name: 'http-prod', display_name: 'HTTP prod' }],
      hiddenFieldIds: ['basic_auth_username', 'basic_auth_password'],
      supportsProfiles: true,
    });
  });

  it('drops inactive rows even if the list payload still includes them', async () => {
    mockApiGet.mockImplementation(async (path: string) => {
      if (path.includes('connector-templates/http')) {
        return {
          id: 'http',
          supportsProfiles: true,
          profileFields: [{ id: 'basic_auth_password', label: 'Basic Auth Password' }],
        };
      }
      if (path.includes('connector-profiles')) {
        expect(path).toContain('include_inactive=false');
        return [
          {
            id: 1,
            connector_type: 'http',
            profile_name: 'http-prod',
            display_name: 'HTTP prod',
            description: null,
            config: {},
            configured_secrets: [],
            is_active: true,
          },
          {
            id: 2,
            connector_type: 'http',
            profile_name: 'http-old',
            display_name: 'HTTP old',
            description: null,
            config: {},
            configured_secrets: [],
            is_active: false,
          },
        ];
      }
      throw new Error(path);
    });

    await expect(fetchConnectorProfilesForPicker('http')).resolves.toEqual({
      profiles: [{ profile_name: 'http-prod', display_name: 'HTTP prod' }],
      hiddenFieldIds: ['basic_auth_password'],
      supportsProfiles: true,
    });
  });
});
