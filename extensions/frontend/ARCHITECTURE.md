# Frontend Extension Architecture

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [Architecture Diagram](#architecture-diagram)
4. [Module Resolution System](#module-resolution-system)
5. [Vite Plugin: Override Resolver](#vite-plugin-override-resolver)
6. [Component Override Mechanism](#component-override-mechanism)
7. [Routing Customization](#routing-customization)
8. [Dependency Resolution](#dependency-resolution)
9. [SASS/SCSS Resolution](#sassscss-resolution)
10. [Extension Utilities](#extension-utilities)
11. [Development Workflow](#development-workflow)
12. [Technical Implementation Details](#technical-implementation-details)

---

## Overview

The `extensions/frontend` is a **standalone React application** that extends and overrides components from `spiffworkflow-frontend` without requiring any modifications to the core application. This architecture enables:

- **Zero Core Changes**: The core `spiffworkflow-frontend` remains completely untouched
- **Standalone Execution**: The extension application runs independently with its own build configuration
- **Automatic Override Resolution**: Components are automatically overridden when present in the extension directory
- **Full Type Safety**: Complete TypeScript support with path aliases and type definitions
- **Hot Module Replacement**: Changes in both extensions and core trigger HMR

### Key Components

```
extensions/frontend/
├── package.json                    # Standalone package with all dependencies
├── vite.config.ts                  # Vite configuration with aliases and plugins
├── tsconfig.json                   # TypeScript path mappings
├── index.html                      # HTML entry point
├── vite-plugin-override-resolver.ts # Custom Vite plugin for override resolution
└── src/
    ├── index.tsx                   # Application entry point
    ├── App.tsx                     # Main app component
    ├── components/                 # Override components
    ├── views/                      # Override views
    ├── services/                   # Override services
    └── utils/                      # Extension utilities (useApi, useConfig, useService)
```

---

## Design Principles

### 1. **Standalone Application**
The extension frontend is a complete, runnable application with:
- Its own `package.json` with all required dependencies
- Independent build process via Vite
- Development server on port 7001 (same as core, run one at a time)
- Own entry point (`index.html` → `src/index.tsx`)
- API proxy to backend (avoids CORS issues)

### 2. **Zero Core Modifications**
The core `spiffworkflow-frontend` directory is never modified. All extension logic is contained within `extensions/frontend`.

### 3. **Path-Based Override Resolution**
Components are overridden by creating files with the same path structure as the core application. The Vite plugin automatically resolves overrides before falling back to core.

### 4. **Alias-Based Core Access**
Core modules are accessed via Vite aliases (`@spiffworkflow-frontend`), enabling:
- Clean import statements
- TypeScript path resolution
- Automatic fallback to core when overrides don't exist

### 5. **Dependency Isolation**
All dependencies are installed in `extensions/frontend/node_modules`, ensuring:
- No dependency conflicts with core
- Independent version management
- Proper resolution of bare module imports from core files

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    extensions/frontend                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Vite Dev Server (port 7001)                  │  │
│  │         + API Proxy → localhost:7000                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         vite-plugin-override-resolver.ts             │  │
│  │                                                       │  │
│  │  Intercepts ALL imports (including between core      │  │
│  │  files) and checks for overrides in extensions/src   │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│        ┌─────────────────┼─────────────────┐                │
│        ▼                 ▼                 ▼                │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐           │
│  │  Core →   │    │ Extension │    │   Bare    │           │
│  │  Core     │    │ imports   │    │  Module   │           │
│  │  imports  │    │           │    │  imports  │           │
│  │           │    │           │    │           │           │
│  │ Check for │    │ Check for │    │ Resolve   │           │
│  │ overrides │    │ overrides │    │ from      │           │
│  │ first!    │    │ first     │    │ local     │           │
│  │           │    │           │    │ node_     │           │
│  │           │    │           │    │ modules   │           │
│  └───────────┘    └───────────┘    └───────────┘           │
│        │                 │                 │                │
│        └─────────────────┴─────────────────┘                │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Bundle Output                           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Override    │  │    Core      │  │   Backend    │
│  Files       │  │   Files      │  │   API        │
│              │  │              │  │              │
│ extensions/  │  │ spiffworkflow│  │ localhost:   │
│ frontend/    │  │ -frontend/   │  │ 7000         │
│ src/         │  │ src/         │  │              │
│              │  │              │  │ (via proxy)  │
│ SpiffLogo.tsx│  │ SideNav.tsx  │  │              │
│ (custom)     │  │ (uses        │  │              │
│              │  │  override!)  │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Deep Override Flow Example

```
1. Core SideNav.tsx imports "./SpiffLogo"
                    │
                    ▼
2. Override Resolver intercepts import
                    │
                    ▼
3. Calculates path: "components/SpiffLogo"
                    │
                    ▼
4. Checks: extensions/frontend/src/components/SpiffLogo.tsx
                    │
                    ▼
5. Override exists? YES → Use extensions/frontend/src/components/SpiffLogo.tsx
                   NO  → Use spiffworkflow-frontend/src/components/SpiffLogo.tsx
```

---

## Module Resolution System

The module resolution system is the core of the extension architecture. It enables **automatic component overriding** at any level of the import chain, seamlessly intercepting imports from both extension and core files.

### Key Feature: Deep Override Resolution

The resolver intercepts **all imports** - including imports between core files. This means:

- When core's `SideNav.tsx` imports `./SpiffLogo`, the resolver checks for an override
- If `extensions/frontend/src/components/SpiffLogo.tsx` exists, it's used instead
- **No need to manually override intermediate components** in the import chain

### Resolution Flow

```
Import Statement (from ANY file)
      │
      ▼
┌─────────────────────────────────────┐
│  Is importer in spiffworkflow-      │
│  frontend/src/ ?                    │
└─────────────────────────────────────┘
      │                    │
      │ Yes                │ No (in extensions)
      ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│ Relative import? │  │ Handle normally  │
│ (./Component)    │  │ (extensions      │
└──────────────────┘  │ logic)           │
      │               └──────────────────┘
      │ Yes
      ▼
┌──────────────────┐
│ Calculate path   │
│ relative to core │
│ src directory    │
└──────────────────┘
      │
      ▼
┌──────────────────┐
│ Check for        │
│ override at same │
│ path in          │
│ extensions/src/  │
└──────────────────┘
      │
      ▼
┌──────────────────┐
│ Override exists? │
└──────────────────┘
      │
   Yes│        No
      ▼         ▼
┌─────────┐  ┌─────────────┐
│ Use     │  │ Use core    │
│override │  │ file        │
└─────────┘  └─────────────┘
```

### Resolution Rules

1. **Relative Imports from Core Files** (`./SpiffLogo` in `SideNav.tsx`)
   - Calculates relative path from core's `src/` directory
   - Checks if override exists at same path in `extensions/frontend/src/`
   - If override exists: uses override
   - If no override: lets Vite resolve to core file

2. **Relative Imports from Extension Files** (`./Component`)
   - First checks: `extensions/frontend/src/` (relative to importer)
   - Falls back to: `spiffworkflow-frontend/src/` (same relative path)

3. **Alias Imports** (`@spiffworkflow-frontend/components/SpiffLogo`)
   - First checks: `extensions/frontend/src/components/SpiffLogo.tsx`
   - Falls back to: `spiffworkflow-frontend/src/components/SpiffLogo.tsx`

4. **Bare Module Imports** (`jwt-decode`, `@mui/material`)
   - If importer is from `spiffworkflow-frontend/`, resolves from `extensions/frontend/node_modules`
   - Otherwise, uses standard Vite resolution

5. **Asset Imports** (`.css`, `.scss`, `.svg`, `.png`, etc.)
   - Override check first (if exists in extensions)
   - Falls back to core asset via alias

---

## Vite Plugin: Override Resolver

The `vite-plugin-override-resolver.ts` is a custom Vite plugin that implements the override resolution logic. It runs with `enforce: 'pre'` to ensure it processes imports before other plugins.

### Plugin Structure

```typescript
export function overrideResolver(): Plugin {
  const extensionsDir = path.resolve(__dirname, './src');
  const coreDir = path.resolve(__dirname, '../../spiffworkflow-frontend/src');
  const localNodeModules = path.resolve(__dirname, './node_modules');

  return {
    name: 'override-resolver',
    enforce: 'pre',  // Run before other plugins
    resolveId(source, importer, options) {
      // Resolution logic here
    },
  };
}
```

### Resolution Logic

#### 1. Relative Imports from Core Files (Deep Override)

**This is the key feature.** When a core file imports another file with a relative path, we check for overrides:

```typescript
// Handle relative imports from CORE files - check for overrides
if (importerInCore && source.startsWith('.')) {
  const importerDir = path.dirname(importer);
  const resolvedCorePath = path.resolve(importerDir, source);
  
  // Get the relative path from core src directory
  const relativePath = path.relative(coreDir, resolvedCorePath);
  
  // Check if override exists
  const overridePath = findOverride(relativePath);
  if (overridePath) {
    return overridePath;  // Use the override!
  }

  // No override, let Vite resolve normally
  return null;
}
```

**Example**: When `spiffworkflow-frontend/src/components/SideNav.tsx` imports `./SpiffLogo`:
1. Resolver detects importer is in core
2. Calculates relative path: `components/SpiffLogo`
3. Checks if `extensions/frontend/src/components/SpiffLogo.tsx` exists
4. If yes, returns the override path

#### 2. Bare Module Resolution (from Core Files)

When a file in `spiffworkflow-frontend` imports a bare module (e.g., `import { jwtDecode } from 'jwt-decode'`), Vite needs to resolve it from `extensions/frontend/node_modules`:

```typescript
// Handle bare module imports from spiffworkflow-frontend files
if (importerInCore && !source.startsWith('.') && !source.startsWith('/')) {
  // Resolve to local node_modules
  return this.resolve(source, path.resolve(extensionsDir, 'index.tsx'), { 
    skipSelf: true 
  });
}
```

#### 3. Relative Imports from Extension Files

For relative imports within extensions:

```typescript
if (importerInExtensions && source.startsWith('.')) {
  // Check if local override exists
  const overridePath = findOverride(relativePath);
  if (overridePath) {
    return overridePath;
  }

  // Fallback to core
  const corePath = findInCore(relativePath);
  if (corePath) {
    return corePath;
  }
}
```

#### 4. Alias Import Resolution

When importing from `@spiffworkflow-frontend`:

```typescript
if (source.startsWith('@spiffworkflow-frontend')) {
  const cleanPath = source.replace('@spiffworkflow-frontend', '').slice(1);
  
  // Check for override first
  const overridePath = findOverride(cleanPath);
  if (overridePath) {
    return overridePath;
  }

  // No override - return null to let Vite's alias handle it
  return null;
}
```

### Plugin Configuration

The plugin is configured in `vite.config.ts`:

```typescript
plugins: [
  overrideResolver(),  // Must be first
  preact({ devToolsEnabled: false }),
  svgr({ /* ... */ }),
],
```

---

## Component Override Mechanism

### How Overrides Work

1. **Path Matching**: Override files must match the exact path structure of core files
2. **Deep Override Resolution**: The Vite plugin intercepts **all imports** (including between core files) and checks for overrides
3. **No Intermediate Overrides Needed**: You only need to override the component you want to change, not its parent components
4. **Interface Compatibility**: Override components should maintain the same interface (props, return types) as core

### Deep Override Example

When you create `extensions/frontend/src/components/SpiffLogo.tsx`, it's automatically used **everywhere** in the application - even when core files import it:

```
Core Import Chain:
ContainerForExtensions.tsx → SideNav.tsx → SpiffLogo.tsx
                                              ↓
                              Override resolver intercepts!
                                              ↓
                              extensions/frontend/src/components/SpiffLogo.tsx
```

**You don't need to override `SideNav.tsx` or `ContainerForExtensions.tsx`** - the resolver automatically uses your override.

### Override Examples

#### Example 1: Simple Override

**Core**: `spiffworkflow-frontend/src/components/SpiffLogo.tsx`
```typescript
export default function SpiffLogo() {
  return <div>Spiff Logo</div>;
}
```

**Override**: `extensions/frontend/src/components/SpiffLogo.tsx`
```typescript
export default function SpiffLogo() {
  return <div>M8Flow</div>;
}
```

**Result**: Every component that imports `SpiffLogo` (including core components) will use your override automatically.

#### Example 2: Wrapping Core Component

```typescript
// extensions/frontend/src/components/SpiffLogo.tsx
import CoreSpiffLogo from '@spiffworkflow-frontend/components/SpiffLogo';
import { useConfig } from '../utils/useConfig';

export default function SpiffLogo() {
  const config = useConfig();
  
  return (
    <div>
      <CoreSpiffLogo />
      <span>Environment: {config.SPIFF_ENVIRONMENT}</span>
    </div>
  );
}
```

#### Example 3: Conditional Override

```typescript
// extensions/frontend/src/components/SpiffLogo.tsx
import CoreSpiffLogo from '@spiffworkflow-frontend/components/SpiffLogo';
import { useConfig } from '../utils/useConfig';

export default function SpiffLogo() {
  const config = useConfig();
  
  if (config.SPIFF_ENVIRONMENT === 'production') {
    return <div>Production Logo</div>;
  }
  
  return <CoreSpiffLogo />;
}
```

### Overrideable Modules

You can override:
- **Components**: `src/components/ComponentName.tsx`
- **Views**: `src/views/ViewName.tsx`
- **Services**: `src/services/ServiceName.ts`
- **Hooks**: `src/hooks/useHookName.tsx`
- **Utilities**: `src/utils/utilityName.ts`
- **Assets**: `src/assets/assetName.svg` (CSS, SCSS, images, etc.)

---

## Routing Customization

The extension architecture allows you to add custom routes to the application by overriding the `ContainerForExtensions` component. This is useful for adding entirely new pages to the application.

### How Routing Works

The application's routing is structured in layers:

1. **App.tsx** - Top-level router using React Router's `createBrowserRouter`
2. **ContainerForExtensions.tsx** - Contains the main application routes within a `<Routes>` component
3. **BaseRoutes.tsx** - Core application routes (homepage, process models, tasks, etc.)

### Adding Custom Routes

To add a new route (e.g., `/reports`), follow these steps:

#### Step 1: Create the Page Component

Create a new view component in `extensions/frontend/src/views/`:

```typescript
// extensions/frontend/src/views/ReportsPage.tsx
import { Box, Typography } from '@mui/material';

export default function ReportsPage() {
  return (
    <Box sx={{ padding: 3 }}>
      <Typography variant="h4" component="h1">
        Reports Page
      </Typography>
    </Box>
  );
}
```

#### Step 2: Create ContainerForExtensions Override

Create an override of `ContainerForExtensions.tsx`:

```typescript
// extensions/frontend/src/ContainerForExtensions.tsx
// Copy the entire contents from spiffworkflow-frontend/src/ContainerForExtensions.tsx
// Then modify the imports and add your route
```

Key changes required:

1. **Change all imports** from relative paths to use the `@spiffworkflow-frontend` alias:

```typescript
// Change from:
import SideNav from './components/SideNav';
import BaseRoutes from './views/BaseRoutes';

// To:
import SideNav from '@spiffworkflow-frontend/components/SideNav';
import BaseRoutes from '@spiffworkflow-frontend/views/BaseRoutes';
```

2. **Import your new page component**:

```typescript
import ReportsPage from './views/ReportsPage';
```

3. **Add your route** to the `routeComponents()` function:

```typescript
const routeComponents = () => {
  return (
    <Routes>
      {/* Custom routes - add before the catch-all */}
      <Route path="reports" element={<ReportsPage />} />
      
      {/* Existing routes */}
      <Route path="extensions/:page_identifier" element={<Extension />} />
      <Route path="login" element={<Login />} />
      
      {/* Catch-all route must be last */}
      <Route
        path="*"
        element={
          <BaseRoutes
            extensionUxElements={extensionUxElements}
            setAdditionalNavElement={setAdditionalNavElement}
            isMobile={isMobile}
          />
        }
      />
    </Routes>
  );
};
```

#### Step 3: Update App.tsx Import

**Important**: The override resolver may not always intercept the `@spiffworkflow-frontend/ContainerForExtensions` import in `App.tsx`. To ensure your override is used, change the import to use a relative path:

```typescript
// extensions/frontend/src/App.tsx

// Change from:
import ContainerForExtensions from '@spiffworkflow-frontend/ContainerForExtensions';

// To:
import ContainerForExtensions from './ContainerForExtensions';
```

### Route Order Matters

When adding routes, order is important:

1. **Specific routes first**: Add your custom routes (e.g., `reports`, `dashboard`) before the catch-all
2. **Catch-all route last**: The `path="*"` route with `BaseRoutes` should always be last

```typescript
<Routes>
  {/* 1. Custom extension routes */}
  <Route path="reports" element={<ReportsPage />} />
  <Route path="dashboard" element={<DashboardPage />} />
  
  {/* 2. Core specific routes */}
  <Route path="extensions/:page_identifier" element={<Extension />} />
  <Route path="login" element={<Login />} />
  
  {/* 3. Catch-all for BaseRoutes (must be last) */}
  <Route path="*" element={<BaseRoutes ... />} />
</Routes>
```

### Complete Example

Here's a minimal example of adding a `/reports` route:

**1. Create the page** (`extensions/frontend/src/views/ReportsPage.tsx`):

```typescript
import { Box, Typography } from '@mui/material';

export default function ReportsPage() {
  return (
    <Box sx={{ padding: 3 }}>
      <Typography variant="h4" component="h1">
        Reports Page
      </Typography>
    </Box>
  );
}
```

**2. Update App.tsx** (`extensions/frontend/src/App.tsx`):

```typescript
// Use relative import for the override
import ContainerForExtensions from './ContainerForExtensions';
```

**3. Create ContainerForExtensions override** with the new route added to `routeComponents()`.

**4. Access your new page** at `http://localhost:7001/reports`

### Adding Navigation Links

To add a link to your new route in the sidebar, you can either:

1. **Override `SideNav.tsx`** to add a custom navigation item
2. **Use the backend extension system** with `extension_uischema.json` to add `primary_nav_item` entries

### Nested Routes

For nested routes, use React Router's nested route syntax:

```typescript
<Route path="reports">
  <Route index element={<ReportsListPage />} />
  <Route path=":reportId" element={<ReportDetailPage />} />
  <Route path="new" element={<NewReportPage />} />
</Route>
```

This creates:
- `/reports` - Reports list
- `/reports/123` - Report detail
- `/reports/new` - New report form

---

## Dependency Resolution

### Problem

When Vite processes files from `spiffworkflow-frontend`, those files may import bare modules (e.g., `import { jwtDecode } from 'jwt-decode'`). By default, Vite resolves these from the project root's `node_modules`, but since we're importing from outside the project root, we need to explicitly resolve them from `extensions/frontend/node_modules`.

### Solution

The override resolver plugin intercepts bare module imports when the importer is from `spiffworkflow-frontend`:

```typescript
// In vite-plugin-override-resolver.ts
if (importer && importer.includes('/spiffworkflow-frontend/') 
    && !source.startsWith('.') && !source.startsWith('/')) {
  // This is a bare import from a core file
  // Resolve it from extensions/frontend/node_modules
  return this.resolve(source, path.resolve(extensionsDir, 'index.tsx'), { 
    skipSelf: true 
  });
}
```

### How It Works

1. **Detection**: Plugin detects when a file in `spiffworkflow-frontend` imports a bare module
2. **Context Switch**: Uses `this.resolve()` with a fake importer from `extensions/frontend/src/index.tsx`
3. **Resolution**: Vite resolves the module from `extensions/frontend/node_modules`

### Dependency Management

All dependencies must be installed in `extensions/frontend`:

```bash
cd extensions/frontend
npm install
```

The `package.json` should contain all dependencies that are used by:
- Extension code directly
- Core code that is imported by extensions

---

## SASS/SCSS Resolution

### Problem

When importing SCSS files from core (e.g., `@spiffworkflow-frontend/index.scss`), those files may use SASS `@use` or `@import` statements to import from npm packages (e.g., `@use '@carbon/react'`). SASS has its own module resolution system that doesn't automatically know where to find these packages.

### Solution

Configure SASS `loadPaths` in `vite.config.ts`:

```typescript
css: {
  preprocessorOptions: {
    scss: {
      silenceDeprecations: ['mixed-decls'],
      loadPaths: [
        path.resolve(__dirname, './node_modules'),
      ],
    },
  },
},
```

### How It Works

1. **SASS Processing**: When Vite processes a `.scss` file, it uses the SASS compiler
2. **Load Paths**: SASS checks `loadPaths` for `@use` and `@import` statements
3. **Resolution**: SASS finds `@carbon/react` in `extensions/frontend/node_modules/@carbon/react`

### Example

**Core SCSS**: `spiffworkflow-frontend/src/index.scss`
```scss
@use '@carbon/react';
// ... other styles
```

**Resolution**: SASS looks in `extensions/frontend/node_modules/@carbon/react` (via `loadPaths`)

---

## Extension Utilities

Extension utilities provide convenient access to core functionality without direct imports.

### useApi()

Provides access to HTTP service methods:

```typescript
// src/utils/useApi.ts
import HttpService from '@spiffworkflow-frontend/services/HttpService';

export function useApi() {
  return {
    makeCallToBackend: HttpService.makeCallToBackend,
    HttpMethods: HttpService.HttpMethods,
    messageForHttpError: HttpService.messageForHttpError,
  };
}
```

**Usage**:
```typescript
import { useApi } from '../utils/useApi';

function MyComponent() {
  const api = useApi();
  
  useEffect(() => {
    api.makeCallToBackend({
      path: '/api/endpoint',
      successCallback: (data) => console.log(data),
      failureCallback: (error) => console.error(error),
    });
  }, [api]);
}
```

### useConfig()

Provides access to configuration variables:

```typescript
// src/utils/useConfig.ts
import {
  BACKEND_BASE_URL,
  SPIFF_ENVIRONMENT,
  DATE_FORMAT,
  // ... other config values
} from '@spiffworkflow-frontend/config';

export function useConfig() {
  return {
    BACKEND_BASE_URL,
    SPIFF_ENVIRONMENT,
    DATE_FORMAT,
    // ... other config values
  };
}
```

**Usage**:
```typescript
import { useConfig } from '../utils/useConfig';

function MyComponent() {
  const config = useConfig();
  
  return (
    <div>
      <p>Environment: {config.SPIFF_ENVIRONMENT}</p>
      <p>Backend: {config.BACKEND_BASE_URL}</p>
    </div>
  );
}
```

### useService()

Provides access to core services:

```typescript
// src/utils/useService.ts
import UserService from '@spiffworkflow-frontend/services/UserService';

export function useService() {
  return {
    UserService,
  };
}
```

**Usage**:
```typescript
import { useService } from '../utils/useService';

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

---

## Development Workflow

### 1. Initial Setup

```bash
cd extensions/frontend
npm install
```

### 2. Start Development Server

```bash
npm start
```

The server runs on `http://localhost:7001` (same port as core - run one at a time).

**Note**: The extension app uses a Vite proxy to route API requests to the backend (default: `http://localhost:7000`). This avoids CORS issues.

### 3. Create an Override

1. Identify the component to override (e.g., `spiffworkflow-frontend/src/components/SpiffLogo.tsx`)
2. Create the same path in extensions: `extensions/frontend/src/components/SpiffLogo.tsx`
3. Implement your override
4. **That's it!** The override is automatically used everywhere in the application

**No need to override parent components** - the resolver intercepts all imports and uses your override.

### 4. Hot Module Replacement

- Changes to extension files trigger HMR
- Changes to core files (when imported) also trigger HMR
- The override resolver ensures the correct file is loaded

### 5. Build for Production

```bash
npm run build
```

Output is in `dist/` directory.

### 6. Preview Production Build

```bash
npm run serve
```

### 7. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7001` | Dev server port |
| `BACKEND_PORT` | `7000` | Backend API port (for proxy) |
| `HOST` | `localhost` | Dev server host |

Example:
```bash
PORT=7002 BACKEND_PORT=8000 npm start
```

---

## Technical Implementation Details

### Vite Configuration

**File**: `extensions/frontend/vite.config.ts`

Key configurations:

1. **Plugin Order** (must be first):
```typescript
plugins: [
  overrideResolver(),  // Must be first for override resolution
  preact({ devToolsEnabled: false }),
  svgr({ /* ... */ }),
]
```

2. **API Proxy** (avoids CORS issues):
```typescript
server: {
  port: 7001,
  proxy: {
    '/v1.0': {
      target: `http://localhost:${backendPort}`,
      changeOrigin: true,
      secure: false,
    },
    '/api': {
      target: `http://localhost:${backendPort}`,
      changeOrigin: true,
      secure: false,
    },
  },
}
```

3. **Aliases**:
```typescript
resolve: {
  alias: {
    '@spiffworkflow-frontend': path.resolve(__dirname, '../../spiffworkflow-frontend/src'),
    '@spiffworkflow-frontend-assets': path.resolve(__dirname, '../../spiffworkflow-frontend/src/assets'),
  },
  preserveSymlinks: true,
}
```

4. **SASS Load Paths**:
```typescript
css: {
  preprocessorOptions: {
    scss: {
      loadPaths: [
        path.resolve(__dirname, './node_modules'),
      ],
    },
  },
}
```

### TypeScript Configuration

**File**: `extensions/frontend/tsconfig.json`

Key configurations:

1. **Path Mappings**:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@spiffworkflow-frontend/*": ["../spiffworkflow-frontend/src/*"],
      "@spiffworkflow-frontend-assets/*": ["../spiffworkflow-frontend/src/assets/*"]
    }
  }
}
```

2. **No Project References**: Project references are not used to avoid conflicts with `vite-tsconfig-paths`.

### Entry Point

**File**: `extensions/frontend/src/index.tsx`

The entry point:
1. Imports core styles and i18n via aliases
2. Sets up React root
3. Configures MUI theme
4. Renders the App component

### Application Component

**File**: `extensions/frontend/src/App.tsx`

The main app component:
1. Imports core contexts and components via aliases
2. Sets up routing
3. Configures providers (QueryClient, APIError, Ability)
4. Uses `ContainerForExtensions` from core

### File Extension Resolution

The plugin checks for files in this order:
1. `.tsx`
2. `.ts`
3. `.jsx`
4. `.js`
5. `/index.tsx`
6. `/index.ts`

---

## Summary

The frontend extension architecture enables:

✅ **Standalone Application**: Runs independently with its own build process  
✅ **Zero Core Changes**: No modifications to `spiffworkflow-frontend`  
✅ **Deep Override Resolution**: Override any component - resolver intercepts ALL imports including between core files  
✅ **No Intermediate Overrides**: Only override the component you need, not parent components  
✅ **Full Type Safety**: Complete TypeScript support  
✅ **Dependency Isolation**: All dependencies in extension's `node_modules`  
✅ **API Proxy**: Built-in proxy avoids CORS issues with backend  
✅ **SASS Resolution**: Proper resolution of SASS modules  
✅ **Hot Reload**: Changes in both extensions and core trigger HMR  

The architecture is built on:
- **Vite** for fast development and optimized builds
- **Custom Vite Plugin** for deep override resolution
- **API Proxy** for seamless backend communication
- **Path Aliases** for clean imports
- **TypeScript Path Mappings** for type safety
- **Extension Utilities** for convenient core access

### Quick Example

To change the logo from "Spiffworkflow" to "M8Flow":

1. Create `extensions/frontend/src/components/SpiffLogo.tsx`
2. Implement your custom logo component
3. Run `npm start` - your logo appears everywhere automatically!
