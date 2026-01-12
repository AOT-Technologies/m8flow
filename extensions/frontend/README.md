# M8Flow Frontend Extensions

This directory contains all AOT Technologies customizations for the M8Flow frontend.

## 🎯 Key Principle

**NEVER modify code in `spiffworkflow-frontend/src/`**. All customizations must be implemented as extensions in this directory.

## 📁 Directory Structure

```
extensions/frontend/
├── components/          # Reusable UI components (M8FlowLogo, VerificationBanner, etc.)
├── views/              # Full page views (SampleView, etc.)
├── hooks/              # Custom React hooks
├── services/           # Business logic services
├── themes/             # Custom styling and themes
├── plugins/            # Extension points and plugin system
├── config/             # Extension configuration (variants, etc.)
├── types/              # TypeScript type definitions
├── utils/              # Utility functions
├── contexts/           # React contexts (ExtensionContext)
├── runtime/            # Runtime injection system
│   ├── wrapper.tsx     # Main wrapper HOC
│   └── injectors/      # Portal-based injectors (Logo, Navigation, Routes)
├── tests/              # Extension-specific tests
├── index.tsx           # Entry point
├── vite.config.ts      # Vite configuration
└── package.json        # Standalone package configuration
```

## 🚀 Quick Start

### Prerequisites

1. **Install upstream dependencies first**:
   ```bash
   cd ../../spiffworkflow-frontend
   npm install
   ```

2. **Then install extension dependencies**:
   ```bash
   cd ../../extensions/frontend
   npm install
   ```

### Development

```bash
cd extensions/frontend
npm start
```

This will start the dev server with M8Flow extensions active at `http://localhost:7001`.

**Note**: If you get a 404 error, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

### Build

```bash
# M8Flow build (with extensions)
npm run build:m8flow

# Spiff build (pure upstream)
npm run build:spiff
```

## 🔌 Extension System

### How It Works

The extension system uses **runtime injection** to customize the upstream SpiffWorkflow app without modifying any upstream code:

1. **Wrapper HOC**: Wraps the upstream `App` component
2. **React Portals**: Injects custom components into specific DOM locations
3. **Extension Context**: Provides feature flags and variant configuration
4. **Route Interception**: Handles custom routes without modifying upstream routing

### Extension Points

#### 1. Logo Injection

The `LogoInjector` replaces the SpiffWorkflow logo with M8Flow branding using React Portal.

#### 2. Navigation Injection

The `NavigationInjector` adds custom navigation items to the sidebar.

#### 3. Route Injection

The `RouteInjector` handles custom routes (e.g., `/sample-page`) and renders custom views.

#### 4. Component Extensions

Create reusable components in `components/` and import them using `@m8flow/components`.

## 📝 Creating Extensions

### Example: Adding a Custom Component

1. **Create the component**:

```typescript
// extensions/frontend/components/MyComponent.tsx
import React from 'react';

export const MyComponent: React.FC = () => {
  return <div>My Custom Component</div>;
};
```

2. **Export it**:

```typescript
// extensions/frontend/components/index.ts
export { MyComponent } from './MyComponent';
```

3. **Use it**:

```typescript
import { MyComponent } from '@m8flow/components';
```

### Example: Adding a Custom Route

1. **Create the view**:

```typescript
// extensions/frontend/views/MyView.tsx
import React from 'react';

export const MyView: React.FC = () => {
  return <div>My Custom View</div>;
};
```

2. **Update RouteInjector** to handle the new route:

```typescript
// extensions/frontend/runtime/injectors/RouteInjector.tsx
if (location.pathname === '/my-route') {
  return createPortal(<MyView />, mainContent);
}
```

3. **Add navigation item** (optional):

Update `NavigationInjector` to add a sidebar link.

## 🧪 Testing

```bash
npm test
```

Tests verify:
- Zero-touch: No upstream files modified
- Extension components work correctly
- Integration points function properly

## 🔄 Development Workflow

1. **Start dev server**: `npm start` from `extensions/frontend/`
2. **Make changes**: Edit files in `extensions/frontend/`
3. **Hot reload**: Changes reflect automatically (<1s)
4. **Test**: Run `npm test` to verify
5. **Build**: Run `npm run build:m8flow` for production

## 🐛 Troubleshooting

### Extensions Not Loading

- Check Vite config has correct aliases
- Verify import paths use `@m8flow/*` prefix
- Check for TypeScript errors: `npm run typecheck`

### Portal Injection Not Working

- Ensure DOM is ready (injectors wait for elements)
- Check browser console for errors
- Verify selectors match upstream DOM structure

### Routes Not Working

- Verify route path matches in `RouteInjector`
- Check React Router location matches
- Ensure main content container is found

## 📚 Additional Resources

- [Vite Documentation](https://vitejs.dev/)
- [React Documentation](https://react.dev/)
- [Material-UI Documentation](https://mui.com/)
- [SpiffArena Documentation](https://spiff-arena.readthedocs.io/)
