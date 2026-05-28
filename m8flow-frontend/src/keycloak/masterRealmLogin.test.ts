import { describe, expect, it } from 'vitest';

import {
  buildMasterRealmLoginUrl,
  extractBackendBaseUrl,
  extractFrontendOrigin,
} from '../../../m8flow-backend/keycloak/themes/m8flow/login/resources/js/masterRealmLogin.js';

const encodeState = (state: string) => Buffer.from(state, 'utf-8').toString('base64');

describe('masterRealmLogin theme helper', () => {
  it('derives the backend login base from the redirect_uri on the Keycloak login page', () => {
    const currentLocation =
      'http://localhost:7002/realms/m8flow/protocol/openid-connect/auth?redirect_uri=' +
      encodeURIComponent('http://localhost:7000/v1.0/login_return');

    expect(extractBackendBaseUrl(currentLocation)).toBe('http://localhost:7000/v1.0');
  });

  it('prefers the original frontend origin from the encoded login state', () => {
    const state = encodeState(
      "{'final_url': 'http://localhost:7001/reports?tab=active', 'authentication_identifier': 'm8flow'}",
    );
    const currentLocation =
      'http://localhost:7002/realms/m8flow/protocol/openid-connect/auth?state=' +
      encodeURIComponent(state);

    expect(extractFrontendOrigin(currentLocation)).toBe('http://localhost:7001');
  });

  it('builds a master-realm login URL that returns platform admins to organization management', () => {
    const state = encodeState(
      "{'final_url': 'http://localhost:7001/', 'authentication_identifier': 'm8flow'}",
    );
    const currentLocation =
      'http://localhost:7002/realms/m8flow/protocol/openid-connect/auth?' +
      `redirect_uri=${encodeURIComponent('http://localhost:7000/v1.0/login_return')}&` +
      `state=${encodeURIComponent(state)}`;

    expect(buildMasterRealmLoginUrl(currentLocation)).toBe(
      'http://localhost:7000/v1.0/login?redirect_url=http%3A%2F%2Flocalhost%3A7001%2Ftenants&authentication_identifier=master',
    );
  });

  it('builds an m8flow-realm login URL that returns regular users to the app root', () => {
    const state = encodeState(
      "{'final_url': 'http://localhost:7001/tenants', 'authentication_identifier': 'master'}",
    );
    const currentLocation =
      'http://localhost:7002/realms/master/protocol/openid-connect/auth?' +
      `redirect_uri=${encodeURIComponent('http://localhost:7000/v1.0/login_return')}&` +
      `state=${encodeURIComponent(state)}`;

    expect(
      buildMasterRealmLoginUrl(currentLocation, '', {
        masterRealmIdentifier: 'm8flow',
        platformAdminPath: '/',
      }),
    ).toBe(
      'http://localhost:7000/v1.0/login?redirect_url=http%3A%2F%2Flocalhost%3A7001%2F&authentication_identifier=m8flow',
    );
  });

  it('falls back to the backend referrer redirect_url when the state payload does not carry a final_url', () => {
    const currentLocation =
      'http://localhost:7002/realms/m8flow/protocol/openid-connect/auth?' +
      `redirect_uri=${encodeURIComponent('http://localhost:7000/v1.0/login_return')}`;
    const referrer =
      'http://localhost:7000/v1.0/login?' +
      `redirect_url=${encodeURIComponent('http://localhost:7001/process-groups')}`;

    expect(buildMasterRealmLoginUrl(currentLocation, referrer)).toBe(
      'http://localhost:7000/v1.0/login?redirect_url=http%3A%2F%2Flocalhost%3A7001%2Ftenants&authentication_identifier=master',
    );
  });
});
