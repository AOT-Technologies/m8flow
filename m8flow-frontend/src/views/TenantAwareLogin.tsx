/**
 * Coordinates frontend -> backend login redirects.
 *
 * In multitenant mode, fresh tenant-user logins always start against the shared
 * realm without a preselected organization. The first login discovers shared-realm
 * organization memberships; TenantSelectPage then finalizes the single available
 * tenant automatically or asks the user to choose one.
 */
import { useEffect } from 'react';
import { Typography } from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { useConfig } from '../utils/useConfig';
import UserService from '../services/UserService';

export default function TenantAwareLogin() {
  const { ENABLE_MULTITENANT } = useConfig();
  const [searchParams] = useSearchParams();

  const originalUrl = searchParams.get('original_url');
  const requestedAuthIdentifier = (
    searchParams.get('authentication_identifier') || ''
  ).trim();

  useEffect(() => {
    if (!ENABLE_MULTITENANT) {
      if (UserService.isLoggedIn()) {
        globalThis.location.replace('/');
        return;
      }

      UserService.beginAutomaticReauthentication({
        originalUrl,
        requestedAuthenticationIdentifier: requestedAuthIdentifier,
      });
      return;
    }

    if (UserService.isLoggedIn()) {
      globalThis.location.replace(originalUrl || '/');
      return;
    }

    UserService.beginAutomaticReauthentication({
      originalUrl,
      requestedAuthenticationIdentifier: requestedAuthIdentifier,
    });
  }, [
    ENABLE_MULTITENANT,
    requestedAuthIdentifier,
    originalUrl,
  ]);

  return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <Typography>Redirecting to sign in...</Typography>
    </div>
  );
}
