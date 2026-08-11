/**
 * m8flow override: application logo.
 *
 * Replaces upstream's SpiffArena logo with m8flow branding. Resolved in place of
 * spiffworkflow-frontend/src/components/SpiffLogo.tsx by the override resolver,
 * so upstream's own imports of SpiffLogo pick this up.
 *
 * Delete this file to fall back to upstream's logo.
 */
import { Stack } from '@mui/material';

import m8fLogo from '../assets/images/m8fLogo.webp';

export default function SpiffLogo() {
  return (
    <Stack
      direction="row"
      sx={{
        alignItems: 'center',
        gap: 1,
        width: '100%',
        padding: '0.25rem 0.75rem',
      }}
    >
      <img
        src={m8fLogo}
        alt="M8Flow Logo"
        style={{ height: '28px', display: 'block' }}
      />
    </Stack>
  );
}
