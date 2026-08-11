/**
 * m8flow application entry point.
 *
 * Everything below the Faro setup - the MUI theme, the React root, the render
 * tree - is defined upstream by SpiffArena (LGPL-2.1) in its own index.tsx.
 * Rather than carrying a copy of it, this module initialises m8flow's telemetry
 * and then hands over to the upstream entry point.
 *
 * `@spiff-core` always resolves to the upstream original, never back to an
 * m8flow override - see the alias in vite.config.ts. Upstream's own relative
 * imports (./App, ./i18n, ./index.scss) still pass through the override
 * resolver, so m8flow's App and i18n overrides are picked up as before.
 *
 * The import is dynamic on purpose: ES imports are hoisted, so a static
 * `import '@spiff-core/index'` would execute upstream's module-level render
 * BEFORE initFaro() ran, and the first paint would go untracked.
 */
import { initFaro, syncFaroTenantFromCookie } from './faro';

initFaro();
// Tags Faro with the tenant from an already-set m8flow_selected_tenant cookie —
// covers returning users and the post-redirect landing page after tenant
// finalization, not just the in-app selection flow (TenantSelectPage also
// calls this directly when a tenant is newly selected).
syncFaroTenantFromCookie();

// Hands off to upstream, which creates the React root and renders <App />.
import('@spiff-core/index');
