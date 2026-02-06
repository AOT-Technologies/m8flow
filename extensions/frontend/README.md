# Standalone Extension Frontend

This is a **standalone application** that extends and overrides components from `spiffworkflow-frontend` without requiring any changes to the core application.

## Overview

`extensions/frontend` is a complete, runnable application that:
- **Runs independently** with its own build configuration and entry point
- **Imports from core** via Vite aliases (`@spiffworkflow-frontend`)
- **Overrides components** by providing files with the same path structure
- **Requires zero changes** to `spiffworkflow-frontend`

## Architecture

```
extensions/frontend/
├── package.json              # Standalone package with dependencies
├── vite.config.ts            # Vite config with aliases to spiffworkflow-frontend
├── tsconfig.json             # TypeScript config with path mappings
├── index.html                # HTML entry point
├── vite-plugin-override-resolver.ts  # Plugin for automatic override resolution
├── src/
│   ├── index.tsx             # Application entry point
│   ├── App.tsx               # Main app component (imports from @spiffworkflow-frontend)
│   ├── components/           # Override components here
│   │   └── SpiffLogo.tsx
│   ├── views/               # Override views here
│   ├── services/            # Override services here
│   ├── hooks/               # Override hooks here
│   └── utils/               # Extension utilities
│       ├── useApi.ts
│       ├── useConfig.ts
│       └── useService.ts
└── public/                   # Public assets
```

## Quick Start

### 1. Install Dependencies

```bash
cd extensions/frontend
npm install
```

### 2. Start Development Server

```bash
npm start
```

The application will run on `http://localhost:7001` (same port as core).

**Note**: The extension app uses a Vite proxy to route API requests to the backend (default: `http://localhost:7000`). This avoids CORS issues. The backend URL is automatically configured to use relative paths (`/v1.0`) which go through the proxy.

**To run on a different port**:
```bash
PORT=7002 npm start
```

**To use a different backend port**:
```bash
BACKEND_PORT=8000 npm start
```

### Multitenant mode

When multitenant mode is enabled, the app shows a tenant selection page as the default at `/`. The user enters a tenant name, which is stored in localStorage and then redirected to the login page (Keycloak flow).

**Environment variable**

- **Env variable:** `MULTI_TENANT_ON=true` or `MULTI_TENANT_ON=false` (default: false if unset). The extensions frontend start script passes it to Vite as `VITE_MULTI_TENANT_ON`.
- **Runtime (optional):** set `window.spiffworkflowFrontendJsenv.MULTI_TENANT_ON = 'true'` in `index.html` or server-injected script to enable without a rebuild.

**Example:**
```bash
MULTI_TENANT_ON=true npm start
```

**Behavior**

- When `ENABLE_MULTITENANT` is **true**: `/` and `/tenant` show the tenant selection page. User submits tenant name → stored in localStorage under key `m8flow_tenant` → redirect to `/login`.
- When `ENABLE_MULTITENANT` is **false**: `/` shows the normal home (BaseRoutes). `/tenant` redirects to `/`. The tenant page is hidden.

**Local storage key**

The selected tenant name is stored under **`m8flow_tenant`**. This key can be used later (e.g. by the frontend or backend) to send the tenant in requests (e.g. `X-Tenant` header) for realm-specific login.

### 3. Create an Override

To override a component, create a file in `src/components/` with the same name as the core component:

**Example: Override SpiffLogo**

Create `src/components/SpiffLogo.tsx`:

```typescript
import { Stack, Typography } from '@mui/material';

export default function SpiffLogo() {
  return (
    <Stack direction="row" sx={{ alignItems: 'center', gap: 2 }}>
      <Typography variant="h6">
        M8Flow
      </Typography>
    </Stack>
  );
}
```

### 4. That's It! (Deep Override Resolution)

**Your override is automatically used everywhere in the application** - even in core components that import `SpiffLogo`.

The override resolver intercepts ALL imports (including between core files) and checks for overrides. You don't need to override intermediate components like `SideNav.tsx` that import `SpiffLogo`.

```
Core Import Chain:
ContainerForExtensions → SideNav → SpiffLogo
                                      ↓
                       Override resolver intercepts!
                                      ↓
                       Your custom SpiffLogo.tsx is used
```

## How Override Resolution Works

The Vite plugin (`vite-plugin-override-resolver.ts`) intercepts **ALL imports** - including imports between core files - and checks for overrides:

1. **Core-to-core imports** (e.g., `SideNav.tsx` imports `./SpiffLogo`):
   - Resolver intercepts the import
   - Checks if `extensions/frontend/src/components/SpiffLogo.tsx` exists
   - If yes: uses your override
   - If no: uses core file

2. **Extension imports** (e.g., `./components/SpiffLogo`):
   - First checks: `extensions/frontend/src/components/SpiffLogo.tsx`
   - Falls back to: `spiffworkflow-frontend/src/components/SpiffLogo.tsx`

3. **Alias imports** (e.g., `@spiffworkflow-frontend/components/SpiffLogo`):
   - First checks for override in: `extensions/frontend/src/components/SpiffLogo.tsx`
   - Falls back to: `spiffworkflow-frontend/src/components/SpiffLogo.tsx`

**Key benefit**: You only need to override the specific component you want to change. No need to override parent components in the import chain.

## Extension Utilities

### useApi()

Access HTTP service methods for making API calls:

```typescript
import { useApi } from './utils/useApi';

function MyComponent() {
  const api = useApi();
  
  useEffect(() => {
    api.makeCallToBackend({
      path: '/some/endpoint',
      successCallback: (data) => {
        console.log('Success:', data);
      },
      failureCallback: (error) => {
        console.error('Error:', error);
      },
    });
  }, [api]);
}
```

### useConfig()

Access configuration variables:

```typescript
import { useConfig } from './utils/useConfig';

function MyComponent() {
  const config = useConfig();
  
  return (
    <div>
      <p>Backend URL: {config.BACKEND_BASE_URL}</p>
      <p>Environment: {config.SPIFF_ENVIRONMENT}</p>
      <p>Date Format: {config.DATE_FORMAT}</p>
    </div>
  );
}
```

**Available Config Values:**
- `BACKEND_BASE_URL` - Backend API base URL
- `SPIFF_ENVIRONMENT` - Current environment identifier
- `ENABLE_MULTITENANT` - When true, tenant selection page is the default at `/` (driven by `MULTI_TENANT_ON`; see [Multitenant mode](#multitenant-mode))
- `DARK_MODE_ENABLED` - Whether dark mode is enabled
- `DATE_FORMAT` - Date format string
- `DATE_TIME_FORMAT` - Date and time format
- `DOCUMENTATION_URL` - Documentation URL
- `TASK_METADATA` - Task metadata configuration
- And more (see `spiffworkflow-frontend/src/config.tsx` for full list)

### useService()

Access core services:

```typescript
import { useService } from './utils/useService';

function MyComponent() {
  const services = useService();
  
  const handleLogout = () => {
    services.UserService.doLogout();
  };
  
  return (
    <button onClick={handleLogout}>
      Logout ({services.UserService.getPreferredUsername()})
    </button>
  );
}
```

**Available Services:**
- `UserService` - User authentication and management
  - `isLoggedIn()` - Check if user is logged in
  - `getPreferredUsername()` - Get user's preferred username
  - `getUserEmail()` - Get user's email
  - `doLogout()` - Logout user
  - And more (see `spiffworkflow-frontend/src/services/UserService.ts`)

## Extension Patterns

### Pattern 1: Complete Override

Replace a component entirely:

```typescript
// src/components/SpiffLogo.tsx
export default function SpiffLogo() {
  return <div>My Custom Logo</div>;
}
```

### Pattern 2: Extend/Wrap Component

Wrap the original component with additional functionality:

```typescript
// src/components/SpiffLogo.tsx
import { Stack } from '@mui/material';
import { useConfig } from '../utils/useConfig';
// Import the core component explicitly
import CoreSpiffLogo from '@spiffworkflow-frontend/components/SpiffLogo';

export default function SpiffLogo() {
  const config = useConfig();
  
  return (
    <Stack>
      <CoreSpiffLogo />
      <div>Environment: {config.SPIFF_ENVIRONMENT}</div>
    </Stack>
  );
}
```

### Pattern 3: Conditional Override

Use configuration to conditionally render:

```typescript
import { useConfig } from '../utils/useConfig';
import CoreSpiffLogo from '@spiffworkflow-frontend/components/SpiffLogo';

export default function SpiffLogo() {
  const config = useConfig();
  
  // Only override in specific environments
  if (config.SPIFF_ENVIRONMENT === 'production') {
    return <div>Production Logo</div>;
  }
  
  // Otherwise use core
  return <CoreSpiffLogo />;
}
```

## Overrideable Modules

You can override:

- **Components**: `src/components/ComponentName.tsx`
- **Views**: `src/views/ViewName.tsx`
- **Services**: `src/services/ServiceName.ts`
- **Hooks**: `src/hooks/useHookName.tsx`

The override must:
1. Have the same file name as the core module
2. Be in the corresponding directory structure
3. Export the same interface (props, return type, etc.)

## Import Patterns

### Import Override (Auto-resolved)

```typescript
// This will use override if it exists, otherwise core
import SpiffLogo from './components/SpiffLogo';
```

### Import from Core (Explicit)

```typescript
// Always use core, even if override exists
import CoreSpiffLogo from '@spiffworkflow-frontend/components/SpiffLogo';
```

### Import Assets from Core

```typescript
// Import assets from core
import SpiffIcon from '@spiffworkflow-frontend-assets/icons/spiff-icon-cyan.svg';
```

## TypeScript Support

Full TypeScript support is available:

1. **Path Aliases**: Use `@spiffworkflow-frontend` and `@spiffworkflow-frontend-assets`
   ```typescript
   import { useApi } from './utils/useApi';
   import CoreComponent from '@spiffworkflow-frontend/components/Component';
   ```

2. **Type Definitions**: All types are available from core modules
   ```typescript
   import type { ProcessInstance } from '@spiffworkflow-frontend/interfaces';
   ```

3. **Type Safety**: Extension components should match core component interfaces

## Development Workflow

1. **Start Extension App**: `cd extensions/frontend && npm start`
2. **Create Override**: Add file in `src/components/ComponentName.tsx`
3. **Import in App**: Import using relative path (override takes precedence)
4. **Access Core**: Import from `@spiffworkflow-frontend` when needed
5. **Hot Reload**: Changes in both extensions and core trigger HMR

## Build and Deploy

### Development

```bash
npm start
```

### Production Build

```bash
npm run build
```

The build output will be in `dist/` directory.

### Preview Production Build

```bash
npm run serve
```

## Examples

### Example 1: Custom Homepage

```typescript
// src/views/Homepage.tsx
import { Box, Typography } from '@mui/material';
import { useConfig, useApi } from '../utils';

export default function Homepage() {
  const config = useConfig();
  const api = useApi();
  
  return (
    <Box>
      <Typography variant="h1">
        Welcome to {config.SPIFF_ENVIRONMENT}
      </Typography>
      {/* Your custom homepage content */}
    </Box>
  );
}
```

### Example 2: Enhanced Service

```typescript
// src/services/HttpService.ts
import CoreHttpService from '@spiffworkflow-frontend/services/HttpService';

// Extend the core service
const ExtendedHttpService = {
  ...CoreHttpService,
  
  // Add custom method
  makeCustomCall(path: string) {
    return CoreHttpService.makeCallToBackend({
      path,
      successCallback: (data) => console.log(data),
    });
  },
};

export default ExtendedHttpService;
```

### Example 3: Custom Hook

```typescript
// src/hooks/useCustomData.tsx
import { useState, useEffect } from 'react';
import { useApi } from '../utils/useApi';

export function useCustomData() {
  const [data, setData] = useState(null);
  const api = useApi();
  
  useEffect(() => {
    api.makeCallToBackend({
      path: '/custom/endpoint',
      successCallback: setData,
    });
  }, [api]);
  
  return data;
}
```

## Best Practices

1. **Maintain Compatibility**: Keep the same props/interface as core components
2. **Use Utilities**: Always use `useApi`, `useConfig`, `useService` instead of direct imports
3. **Document Overrides**: Document why you're overriding and what changes you made
4. **Test Thoroughly**: Test overrides in different environments
5. **Error Handling**: Always handle errors in API calls and component logic
6. **Type Safety**: Use TypeScript types from core modules

## Troubleshooting

### Extension Not Loading

1. Check that the file exists in the correct directory (`src/components/`, etc.)
2. Verify the file name matches the core module exactly
3. Check browser console for errors
4. Ensure Vite plugin is loaded in `vite.config.ts`

### TypeScript Errors

1. Ensure path aliases are configured in `tsconfig.json`
2. Check that imports use `@spiffworkflow-frontend` alias
3. Verify types match core component interfaces

### Build Errors

1. Check Vite plugin is loaded in `vite.config.ts`
2. Verify extension directory structure
3. Check for circular dependencies
4. Ensure all dependencies are installed

### Import Resolution Issues

1. Check that `vite-plugin-override-resolver.ts` is in plugins array (first)
2. Verify alias configuration in `vite.config.ts`
3. Check file extensions match (.tsx, .ts, .jsx, .js)

## Key Differences from Previous Architecture

- **Standalone Application**: Runs independently, not as part of core
- **No Core Changes**: Zero modifications to `spiffworkflow-frontend`
- **Automatic Resolution**: Vite plugin handles override resolution
- **Full Control**: Complete control over application structure and entry point

## Support

For issues or questions:
1. Check this documentation
2. Review core component implementations in `spiffworkflow-frontend`
3. Check browser console for errors
4. Review Vite build output
