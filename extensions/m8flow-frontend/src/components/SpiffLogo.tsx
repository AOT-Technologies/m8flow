/**
 * Example Extension Component - SpiffLogo Override
 * 
 * This component overrides the core SpiffLogo component.
 * 
 * This is an example demonstrating:
 * - How to override a core component
 * - How to use extension utilities (useConfig)
 * - How to access configuration variables
 * 
 * To use this override, import it in your App or other components:
 *   import SpiffLogo from './components/SpiffLogo';
 * 
 * The Vite plugin will automatically resolve this override before
 * falling back to the core component.
 */

import { Stack, Typography } from '@mui/material';
import m8fLogo from "../assets/images/m8fLogo.webp";

/**
 * Extended SpiffLogo component that uses configuration
 * 
 * This is an example of how to override a core component.
 * The component has access to all extension utilities including
 * useConfig, useApi, and useService hooks.
 * 
 * Note: This example removes the icon import since it's not available
 * in the extensions directory. In a real override, you could:
 * 1. Import the icon from core: import SpiffIcon from '@spiffworkflow-frontend-assets/icons/spiff-icon-cyan.svg';
 * 2. Use a custom icon
 * 3. Or wrap the core component
 */
export default function SpiffLogo() {
  
  return (
    <Stack
      direction="row"
      sx={{
        alignItems: 'center',
        gap: 2,
        width: '100%',
      }}
    >
      <img src={m8fLogo} alt="M8Flow Logo" style={{ height: "180px" }} />

      {/* Example: Using config in extension component */}
      {/* <Typography
        sx={{
          color: "primary.main",
          fontSize: 22,
          display: { xs: "none", md: "block" },
        }}
      >
        M8Flow
      </Typography> */}
    </Stack>
  );
}
