/**
 * M8Flow app shell orchestrator — composes chrome, bootstrap, routes, and gates.
 * Intentionally structured differently from upstream ContainerForExtensions.
 */
import './tenantLogoutPatch';

import {
  Box,
  CssBaseline,
  IconButton,
  ThemeProvider,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import { useEffect, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router-dom';
import { ErrorBoundary } from 'react-error-boundary';
import { ErrorBoundaryFallback } from '@spiffworkflow-frontend/ErrorBoundaryFallack';
import { UiSchemaDisplayLocation, UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import useAPIError from '@spiffworkflow-frontend/hooks/UseApiError';
import ScrollToTop from '@spiffworkflow-frontend/components/ScrollToTop';
import DynamicCSSInjection from '@spiffworkflow-frontend/components/DynamicCSSInjection';
import BackendIsDown from '@spiffworkflow-frontend/views/BackendIsDown';
import FrontendAccessDenied from '@spiffworkflow-frontend/views/FrontendAccessDenied';

import { pushFaroError } from './faro';
import SideNav from './components/SideNav';
import { useUriListForPermissions } from './hooks/UriListForPermissions';
import UserService from './services/UserService';
import { GlobalTenantProvider } from './contexts/GlobalTenantContext';
import { useConfig } from './utils/useConfig';
import { resolveContainerContentState } from './utils/containerContentState';
import { M8FLOW_TENANT_STORAGE_KEY } from './views/TenantSelectPage';
import { M8flowAppRoutes } from './m8flowAppRoutes';
import { NavActiveHighlightStyles } from './navActiveHighlightStyles';
import { useAppShellChrome } from './useAppShellChrome';
import { useExtensionBootstrap } from './useExtensionBootstrap';

function buildShellPermissionChecks(
  targetUris: ReturnType<typeof useUriListForPermissions>['targetUris'],
): PermissionsToCheck {
  return {
    [targetUris.extensionListPath]: ['GET'],
    [targetUris.processInstanceListForMePath]: ['GET', 'POST'],
    // Requested here so the process-instances route guard resolves once this
    // shell's permissions load, without depending on sibling fetch ordering.
    [targetUris.processInstanceListPath]: ['GET'],
    [targetUris.processGroupListPath]: ['GET'],
    [targetUris.dataStoreListPath]: ['GET'],
    [targetUris.messageInstanceListPath]: ['GET'],
    [targetUris.secretListPath]: ['GET'],
    '/tasks/*': ['GET', 'PUT'],
    [targetUris.m8flowTenantManagementPath]: ['GET'],
    [targetUris.m8flowTenantListPath]: ['GET'],
    [targetUris.m8flowTemplateListPath]: ['GET'],
    [targetUris.connectorsGroupedPath]: ['GET'],
    [targetUris.m8flowMcpConnectionPath]: ['GET'],
    [targetUris.m8flowNatsEventsPath]: ['GET'],
  };
}

function useShellSideEffects(pathname: string, removeError: () => void) {
  useEffect(() => {
    document.querySelector('.cds--white')?.classList.remove('cds--white');
  }, []);

  useEffect(() => {
    removeError();
    // removeError identity is unstable; omitting it avoids an update loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    if (!UserService.isSuperAdmin() || typeof window === 'undefined') {
      return;
    }
    localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
    localStorage.removeItem('m8f_tenant_id');
  }, []);

  useEffect(() => {
    const onTaskCellClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target || target.closest('a,button,[role="button"]')) {
        return;
      }
      const taskCell = target.closest(
        'td[title^="task id:"]',
      ) as HTMLTableCellElement | null;
      const row = taskCell?.closest('tr');
      const taskLink = row?.querySelector(
        'a[href*="/tasks/"]',
      ) as HTMLAnchorElement | null;
      if (!taskLink?.href) {
        return;
      }
      window.location.assign(taskLink.href);
    };

    document.addEventListener('click', onTaskCellClick);
    return () => document.removeEventListener('click', onTaskCellClick);
  }, []);
}

function mergeTenantNavItems(
  base: UiSchemaUxElement[] | null,
  ability: { can: (m: string, u: string) => boolean },
  tenantListPath: string,
  tenantsLabel: string,
): UiSchemaUxElement[] {
  const items = [...(base || [])];
  const showTenantsNav =
    UserService.isSuperAdmin() && ability.can('GET', tenantListPath);
  if (showTenantsNav) {
    items.push({
      page: '/../tenants',
      label: tenantsLabel,
      display_location: UiSchemaDisplayLocation.primary_nav_item,
    } as UiSchemaUxElement);
  }
  return items;
}

function ShellBody({
  backendIsUp,
  canAccessFrontend,
  pathname,
  routeTree,
}: {
  backendIsUp: boolean | null;
  canAccessFrontend: boolean;
  pathname: string;
  routeTree: ReactNode;
}) {
  const contentState = resolveContainerContentState({
    backendIsUp,
    canAccessFrontend,
    isLoggedIn: UserService.isLoggedIn(),
    pathname,
  });

  switch (contentState) {
    case 'loading':
      return null;
    case 'backend-down':
      return <BackendIsDown key="backendIsDownPage" />;
    case 'frontend-access-denied':
      return <FrontendAccessDenied key="frontendAccessDeniedPage" />;
    case 'session-expired-recovery': {
      const encodedOriginalUrl = UserService.getCurrentLocation();
      return (
        <Navigate
          key="sessionExpiredRecoveryPage"
          to={`/login?original_url=${encodedOriginalUrl}`}
          replace
        />
      );
    }
    case 'routes':
    default:
      return routeTree;
  }
}

export default function ContainerForExtensions() {
  const { t } = useTranslation();
  const {
    ENABLE_MULTITENANT,
    NATS_MONITORING_ENABLED,
    MCP_CONNECTION_ENABLED,
  } = useConfig();
  const location = useLocation();
  const { removeError } = useAPIError();
  const { targetUris } = useUriListForPermissions();
  const { ability, permissionsLoaded } = usePermissionFetcher(
    buildShellPermissionChecks(targetUris),
  );

  const chrome = useAppShellChrome(location);
  const {
    backendIsUp,
    canAccessFrontend,
    extensionUxElements,
    extensionCssFiles,
  } = useExtensionBootstrap({
    ability,
    permissionsLoaded,
    uris: {
      statusPath: targetUris.statusPath,
      extensionListPath: targetUris.extensionListPath,
    },
  });

  useShellSideEffects(location.pathname, removeError);

  const gateProps = {
    extensionUxElements,
    setAdditionalNavElement: chrome.setAdditionalNavElement,
    isMobile: chrome.isMobile,
    ability,
    targetUris,
    permissionsLoaded,
  };

  const routeTree = (
    <M8flowAppRoutes
      flags={{
        ENABLE_MULTITENANT,
        NATS_MONITORING_ENABLED,
        MCP_CONNECTION_ENABLED,
      }}
      gateProps={gateProps}
      ability={ability}
      targetUris={targetUris}
      permissionsLoaded={permissionsLoaded}
    />
  );

  const navUxElements = mergeTenantNavItems(
    extensionUxElements,
    ability,
    targetUris.m8flowTenantListPath,
    t('tenants'),
  );

  return (
    <GlobalTenantProvider>
      <ThemeProvider theme={chrome.globalTheme}>
        <CssBaseline />
        <ScrollToTop />
        {extensionCssFiles.map(({ id, content }) => (
          <DynamicCSSInjection key={id} cssContent={content} id={id} />
        ))}
        <NavActiveHighlightStyles
          pathname={location.pathname}
          theme={chrome.globalTheme}
        />
        <ErrorBoundary
          FallbackComponent={ErrorBoundaryFallback}
          onError={(error) => pushFaroError(error)}
        >
          <Box
            id="container-for-extensions-container"
            data-theme={chrome.globalTheme.palette.mode}
            component="main"
            sx={{
              position: 'absolute',
              inset: 0,
              zIndex: 1000,
              p: '0 !important',
              alignItems: 'center',
            }}
          >
            <Box
              id="container-for-extensions-grid"
              sx={{
                display: 'flex',
                width: '100%',
                height: '100%',
              }}
            >
              <Box
                id="container-for-extensions-box"
                sx={{
                  display: 'flex',
                  width: '100%',
                  height: '100vh',
                  overflow: 'hidden',
                }}
              >
                {chrome.isSideNavVisible ? (
                  <SideNav
                    isCollapsed={chrome.isNavCollapsed}
                    onToggleCollapse={chrome.handleNavToggle}
                    onToggleDarkMode={chrome.flipColorScheme}
                    isDark={chrome.isDark}
                    additionalNavElement={chrome.additionalNavElement}
                    setAdditionalNavElement={chrome.setAdditionalNavElement}
                    extensionUxElements={navUxElements}
                  />
                ) : null}

                {chrome.isMobile && !chrome.isSideNavVisible ? (
                  <IconButton
                    data-testid="mobile-menu-button"
                    onClick={chrome.openMobileNav}
                    sx={{ position: 'absolute', top: 16, right: 16, zIndex: 1300 }}
                  >
                    <MenuIcon />
                  </IconButton>
                ) : null}

                <Box
                  id="container-for-extensions-box-2"
                  className={chrome.transitionStage}
                  sx={{
                    bgcolor: 'background.default',
                    minWidth: 0,
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    flex: '1 1 0%',
                    overflow: 'auto',
                  }}
                  onAnimationEnd={(e) => chrome.onRouteFadeEnd(e.animationName)}
                >
                  <ShellBody
                    backendIsUp={backendIsUp}
                    canAccessFrontend={canAccessFrontend}
                    pathname={location.pathname}
                    routeTree={routeTree}
                  />
                </Box>
              </Box>
            </Box>
          </Box>
        </ErrorBoundary>
      </ThemeProvider>
    </GlobalTenantProvider>
  );
}
