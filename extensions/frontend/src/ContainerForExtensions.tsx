import {
  Box,
  Container,
  CssBaseline,
  IconButton,
  Grid,
  ThemeProvider,
  PaletteMode,
  createTheme,
  useMediaQuery,
} from '@mui/material';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import MenuIcon from '@mui/icons-material/Menu';
import { ReactElement, useEffect, useState } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { ErrorBoundaryFallback } from '@spiffworkflow-frontend/ErrorBoundaryFallack';
import SideNav from './components/SideNav';

import Extension from '@spiffworkflow-frontend/views/Extension';
import { useUriListForPermissions } from '@spiffworkflow-frontend/hooks/UriListForPermissions';
import { PermissionsToCheck, ProcessFile, ProcessModel } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import {
  ExtensionUiSchema,
  UiSchemaDisplayLocation,
  UiSchemaUxElement,
} from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import HttpService from './services/HttpService';
import UserService from './services/UserService';
import BaseRoutes from '@spiffworkflow-frontend/views/BaseRoutes';
import BackendIsDown from '@spiffworkflow-frontend/views/BackendIsDown';
import FrontendAccessDenied from '@spiffworkflow-frontend/views/FrontendAccessDenied';
import Login from '@spiffworkflow-frontend/views/Login';
import TenantAwareLogin from './views/TenantAwareLogin';
import useAPIError from '@spiffworkflow-frontend/hooks/UseApiError';
import ScrollToTop from '@spiffworkflow-frontend/components/ScrollToTop';
import { createSpiffTheme } from '@spiffworkflow-frontend/assets/theme/SpiffTheme';
import DynamicCSSInjection from '@spiffworkflow-frontend/components/DynamicCSSInjection';

// M8Flow Extension: Import Reports page and tenant selection
import ReportsPage from './views/ReportsPage';
import TenantSelectPage, {
  M8FLOW_TENANT_STORAGE_KEY,
} from './views/TenantSelectPage';
import { useConfig } from './utils/useConfig';

// M8Flow Extension: clear tenant from localStorage on logout so next visit shows tenant selection
const originalDoLogout = UserService.doLogout;
UserService.doLogout = () => {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
  }
  originalDoLogout();
};

/** When ENABLE_MULTITENANT: at "/" show TenantSelectPage if no tenant in localStorage, else show default home (BaseRoutes). */
function MultitenantRootGate({
  extensionUxElements,
  setAdditionalNavElement,
  isMobile,
}: {
  extensionUxElements: UiSchemaUxElement[] | null;
  setAdditionalNavElement: (el: ReactElement | null) => void;
  isMobile: boolean;
}) {
  const storedTenant = typeof window !== 'undefined' ? localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY) : null;
  if (storedTenant) {
    return (
      <BaseRoutes
        extensionUxElements={extensionUxElements}
        setAdditionalNavElement={setAdditionalNavElement}
        isMobile={isMobile}
      />
    );
  }
  return <TenantSelectPage />;
}

// M8Flow Extension: Import Tenant page

import TenantPage from "./views/TenantPage";
// m8 Extension: Import Template Gallery and Template Modeler pages

import TemplateGalleryPage from './views/TemplateGalleryPage';
import TemplateModelerPage from './views/TemplateModelerPage';

const fadeIn = 'fadeIn';
const fadeOutImmediate = 'fadeOutImmediate';

export default function ContainerForExtensions() {
  const { ENABLE_MULTITENANT } = useConfig();
  const [backendIsUp, setBackendIsUp] = useState<boolean | null>(null);
  const [canAccessFrontend, setCanAccessFrontend] = useState<boolean>(true);
  const [extensionUxElements, setExtensionUxElements] = useState<
    UiSchemaUxElement[] | null
  >(null);

  const [extensionCssFiles, setExtensionCssFiles] = useState<
    Array<{ content: string; id: string }>
  >([]);

  const { targetUris } = useUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {
    [targetUris.extensionListPath]: ['GET'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );

  const { removeError } = useAPIError();

  const location = useLocation();

  const storedTheme: PaletteMode = (localStorage.getItem('theme') ||
    'light') as PaletteMode;
  const [globalTheme, setGlobalTheme] = useState(
    createTheme(createSpiffTheme(storedTheme)),
  );
  const isDark = globalTheme.palette.mode === 'dark';

  const [displayLocation, setDisplayLocation] = useState(location);
  const [transitionStage, setTransitionStage] = useState('fadeIn');
  const [additionalNavElement, setAdditionalNavElement] =
    useState<ReactElement | null>(null);

  const [isNavCollapsed, setIsNavCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem('isNavCollapsed');
    return stored ? JSON.parse(stored) : false;
  });

  const isMobile = useMediaQuery((theme: any) => theme.breakpoints.down('sm'));
  const [isSideNavVisible, setIsSideNavVisible] = useState<boolean>(!isMobile);

  const toggleNavCollapse = () => {
    if (isMobile) {
      setIsSideNavVisible(!isSideNavVisible);
    } else {
      const newCollapsedState = !isNavCollapsed;
      setIsNavCollapsed(newCollapsedState);
      localStorage.setItem('isNavCollapsed', JSON.stringify(newCollapsedState));
    }
  };

  const toggleDarkMode = () => {
    const desiredTheme: PaletteMode = isDark ? 'light' : 'dark';
    setGlobalTheme(createTheme(createSpiffTheme(desiredTheme)));
    localStorage.setItem('theme', desiredTheme);
  };

  useEffect(() => {
    /**
     * The housing app has an element with a white background
     * and a very high z-index. This is a hack to remove it.
     */
    const element = document.querySelector('.cds--white');
    if (element) {
      element.classList.remove('cds--white');
    }
  }, []);
  // never carry an error message across to a different path
  useEffect(() => {
    removeError();
    // if we include the removeError function to the dependency array of this useEffect, it causes
    // an infinite loop where the page with the error adds the error,
    // then this runs and it removes the error, etc. it is ok not to include it here, i think, because it never changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  /** Respond to transition events, this softens screen changes (UX) */
  useEffect(() => {
    if (location !== displayLocation) {
      // const isComingFromInterstitialOrProgress = /\/interstitial$|\/progress$/.test(displayLocation.pathname);
      // setIsLongFadeIn(
      //   isComingFromInterstitialOrProgress && location.pathname === '/',
      // );
      setTransitionStage(fadeOutImmediate);
    }
    if (transitionStage === fadeOutImmediate) {
      setDisplayLocation(location);
      setTransitionStage(fadeIn);
    }
  }, [location, displayLocation, transitionStage]);

  useEffect(() => {
    if (isMobile) {
      setIsSideNavVisible(false);
    } else {
      setIsSideNavVisible(true);
    }
  }, [isMobile]);

  useEffect(() => {
    const processExtensionResult = (processModels: ProcessModel[]) => {
      const eni: UiSchemaUxElement[] = [];
      const cssFiles: Array<{ content: string; id: string }> = [];

      processModels.forEach((processModel: ProcessModel) => {
        const extensionUiSchemaFile = processModel.files.find(
          (file: ProcessFile) => file.name === 'extension_uischema.json',
        );
        if (extensionUiSchemaFile && extensionUiSchemaFile.file_contents) {
          try {
            const extensionUiSchema: ExtensionUiSchema = JSON.parse(
              extensionUiSchemaFile.file_contents,
            );
            if (
              extensionUiSchema &&
              extensionUiSchema.ux_elements &&
              !extensionUiSchema.disabled
            ) {
              // Process ux elements and extract CSS elements
              extensionUiSchema.ux_elements.forEach(
                (element: UiSchemaUxElement) => {
                  if (
                    element.display_location === UiSchemaDisplayLocation.css
                  ) {
                    // Find the CSS file in the process model files
                    const cssFilename =
                      element.location_specific_configs?.css_file;
                    const cssFile = processModel.files.find(
                      (file: ProcessFile) => file.name === cssFilename,
                    );
                    if (cssFile && cssFile.file_contents) {
                      cssFiles.push({
                        content: cssFile.file_contents,
                        id: `${processModel.id}-${cssFilename}`.replace(
                          /[^a-zA-Z0-9]/g,
                          '-',
                        ),
                      });
                    }
                  } else {
                    // Normal UI element
                    eni.push(element);
                  }
                },
              );
            }
          } catch (_jsonParseError: any) {
            console.error(
              `Unable to get navigation items for ${processModel.id}`,
            );
          }
        }
      });

      if (eni.length > 0) {
        setExtensionUxElements(eni);
      }

      if (cssFiles.length > 0) {
        setExtensionCssFiles(cssFiles);
      }
    };

    type HealthStatus = { ok: boolean; can_access_frontend?: boolean };
    const getExtensions = (response: HealthStatus) => {
      setBackendIsUp(true);

      // Check if user has access to frontend
      if (response.can_access_frontend !== undefined) {
        setCanAccessFrontend(response.can_access_frontend);
      }

      if (!permissionsLoaded) {
        return;
      }
      if (ability.can('GET', targetUris.extensionListPath)) {
        HttpService.makeCallToBackend({
          path: targetUris.extensionListPath,
          successCallback: processExtensionResult,
        });
      } else {
        // set to an empty array so we know that it loaded
        setExtensionUxElements([]);
      }
    };

    HttpService.makeCallToBackend({
      path: targetUris.statusPath,
      successCallback: getExtensions,
      failureCallback: () => setBackendIsUp(false),
    });
  }, [
    targetUris.extensionListPath,
    targetUris.statusPath,
    permissionsLoaded,
    ability,
  ]);

  const routeComponents = () => {
    return (
      <Routes>
        {/* M8Flow Extension: Tenant selection (default when ENABLE_MULTITENANT; gate shows home if tenant in localStorage) */}
        {ENABLE_MULTITENANT && (
          <>
            <Route
              path="/"
              element={
                <MultitenantRootGate
                  extensionUxElements={extensionUxElements}
                  setAdditionalNavElement={setAdditionalNavElement}
                  isMobile={isMobile}
                />
              }
            />
            <Route path="tenant" element={<TenantSelectPage />} />
          </>
        )}
        {!ENABLE_MULTITENANT && (
          <Route path="tenant" element={<Navigate to="/" replace />} />
        )}
        {/* Reports route */}
        <Route path="reports" element={<ReportsPage />} />
        {/* M8Flow Extension: Tenant route */}
        <Route path="/tenants" element={<TenantPage />} />
        {/* m8 Extension: Template Gallery and Template Modeler routes */}
        <Route path="templates/:templateId" element={<TemplateModelerPage />} />
        <Route path="templates" element={<TemplateGalleryPage />} />
        <Route path="extensions/:page_identifier" element={<Extension />} />
        <Route path="login" element={<TenantAwareLogin />} />
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

  const backendIsDownPage = () => {
    return [<BackendIsDown key="backendIsDownPage" />];
  };

  const frontendAccessDeniedPage = () => {
    return [<FrontendAccessDenied key="frontendAccessDeniedPage" />];
  };

  const innerComponents = () => {
    if (backendIsUp === null) {
      return [];
    }
    if (!backendIsUp) {
      return backendIsDownPage();
    }
    if (!canAccessFrontend) {
      return frontendAccessDeniedPage();
    }
    return routeComponents();
  };

  return (
    <ThemeProvider theme={globalTheme}>
      <CssBaseline />
      <ScrollToTop />
      {/* Inject any CSS files from extensions */}
      {extensionCssFiles.map((cssFile) => (
        <DynamicCSSInjection
          key={cssFile.id}
          cssContent={cssFile.content}
          id={cssFile.id}
        />
      ))}

      {/* Manual Highlighting for Tenants Route */}
      {location.pathname === "/tenants" && (
        <style>
          {`
            a[href$="/tenants"] {
              background-color: ${(globalTheme.palette as any).background?.light || "#e3f2fd"} !important;
              color: ${globalTheme.palette.primary.main} !important;
              border-left-width: 4px !important;
              border-style: solid !important;
              border-color: ${globalTheme.palette.primary.main} !important;
            }
            a[href$="/tenants"] .MuiListItemIcon-root {
              color: ${globalTheme.palette.primary.main} !important;
            }
            a[href$="/tenants"] .MuiTypography-root {
              font-weight: bold !important;
            }
          `}
        </style>
      )}
      <ErrorBoundary FallbackComponent={ErrorBoundaryFallback}>
        <Container
          id="container-for-extensions-container"
          maxWidth={false}
          data-theme={globalTheme.palette.mode}
          sx={{
            // Hack to position the internal view over the "old" base components
            position: 'absolute',
            top: 0,
            left: 0,
            alignItems: 'center',
            zIndex: 1000,
            padding: '0px !important',
          }}
        >
          <Grid
            id="container-for-extensions-grid"
            container
            sx={{
              height: '100%',
            }}
          >
            <Box
              id="container-for-extensions-box"
              sx={{
                display: 'flex',
                width: '100%',
                height: '100vh',
                overflow: 'hidden', // Consider removing this if the child's overflow: auto is sufficient
              }}
            >
              {isSideNavVisible && (
                <SideNav
                  isCollapsed={isNavCollapsed}
                  onToggleCollapse={toggleNavCollapse}
                  onToggleDarkMode={toggleDarkMode}
                  isDark={isDark}
                  additionalNavElement={additionalNavElement}
                  setAdditionalNavElement={setAdditionalNavElement}
                  extensionUxElements={[
                    ...(extensionUxElements || []),
                    {
                      page: "/../tenants",
                      label: "Tenants",
                      display_location:
                        UiSchemaDisplayLocation.primary_nav_item,
                    } as UiSchemaUxElement,
                  ]}
                />
              )}
              {isMobile && !isSideNavVisible && (
                <IconButton
                  onClick={() => {
                    setIsSideNavVisible(true);
                    setIsNavCollapsed(false);
                  }}
                  sx={{
                    position: 'absolute',
                    top: 16,
                    right: 16,
                    zIndex: 1300,
                  }}
                >
                  <MenuIcon />
                </IconButton>
              )}
              <Box
                id="container-for-extensions-box-2"
                className={`${transitionStage}`}
                sx={{
                  bgcolor: 'background.default',
                  width: '100%',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  flexGrow: 1,
                  overflow: 'auto', // allow scrolling
                }}
                onAnimationEnd={(e) => {
                  if (e.animationName === fadeOutImmediate) {
                    setDisplayLocation(location);
                    setTransitionStage(fadeIn);
                  }
                }}
              >
                {innerComponents()}
              </Box>
            </Box>
          </Grid>
        </Container>
      </ErrorBoundary>
    </ThemeProvider>
  );
}
