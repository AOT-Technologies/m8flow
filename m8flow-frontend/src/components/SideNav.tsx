/**
 * M8Flow primary drawer orchestrator — composes catalog, access, tenant badge,
 * and bottom chrome. Layout primitives differ from upstream SideNav on purpose.
 */
import {
  useEffect,
  useState,
  type MouseEventHandler,
  type ReactElement,
} from 'react';
import {
  Box,
  Divider,
  IconButton,
  Link as MuiLink,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Tooltip,
  useMediaQuery,
} from '@mui/material';
import {
  ChevronLeft,
  ChevronRight,
  Close as CloseIcon,
} from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SpiffTooltip from '@spiffworkflow-frontend/components/SpiffTooltip';
import ExtensionUxElementForDisplay from '@spiffworkflow-frontend/components/ExtensionUxElementForDisplay';
import type { UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';

import UserService from '../services/UserService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import { useConfig } from '../utils/useConfig';
import SpiffLogo from './SpiffLogo';
import GlobalTenantSelector from './GlobalTenantSelector';
import {
  appendExtensionCatalogEntries,
  buildSideNavCatalog,
  iconForNavKey,
  NAV_IDS,
  resolveActiveNavId,
  secondaryPanelHeightPx,
  type SideNavCatalogEntry,
} from './sideNavCatalog';
import {
  buildSideNavPermissionPlan,
  canSeeNavEntry,
} from './sideNavAccess';
import {
  SideNavTenantBadgeCollapsed,
  SideNavTenantBadgeExpanded,
} from './sideNavTenantBadge';
import {
  SideNavBottomFoot,
  SideNavBottomOverlays,
  useSideNavChromeMenus,
} from './sideNavBottomChrome';

const EXPANDED_WIDTH = 350;
const RAIL_WIDTH = 64;
const ACTIVE_ACCENT = 'primary.main';

const DRAWER_SHELL_SX = {
  position: 'relative' as const,
  overflow: 'hidden' as const,
  height: '100vh',
  flexShrink: 0,
  bgcolor: 'background.nav',
  transition: 'width 0.3s',
  borderRightWidth: 1,
  borderRightStyle: 'solid' as const,
  borderRightColor: '#e0e0e0',
};

type SideNavProps = {
  isCollapsed: boolean;
  onToggleCollapse: MouseEventHandler<HTMLButtonElement>;
  onToggleDarkMode: MouseEventHandler<HTMLButtonElement>;
  isDark: boolean;
  additionalNavElement?: ReactElement | null;
  setAdditionalNavElement: Function;
  extensionUxElements?: UiSchemaUxElement[] | null;
};

function CollapseGlyph({
  collapsed,
  expandLabel,
  collapseLabel,
}: {
  collapsed: boolean;
  expandLabel: string;
  collapseLabel: string;
}) {
  if (collapsed) {
    return (
      <SpiffTooltip title={expandLabel} placement="right">
        <ChevronRight data-testid="expand-primary-nav" />
      </SpiffTooltip>
    );
  }
  return (
    <SpiffTooltip title={collapseLabel} placement="bottom">
      <ChevronLeft data-testid="collapse-primary-nav" />
    </SpiffTooltip>
  );
}

function SideNav(props: SideNavProps) {
  const {
    isCollapsed: railMode,
    onToggleCollapse,
    onToggleDarkMode,
    isDark,
    additionalNavElement,
    setAdditionalNavElement,
    extensionUxElements,
  } = props;

  const narrowViewport = useMediaQuery(
    (theme: { breakpoints: { down: (k: string) => string } }) =>
      theme.breakpoints.down('sm'),
  );
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { NATS_MONITORING_ENABLED, MCP_CONNECTION_ENABLED } = useConfig();

  const permissionPlan = buildSideNavPermissionPlan(targetUris);
  const { ability, permissionsLoaded } = usePermissionFetcher(permissionPlan);

  const [tenantId, setTenantId] = useState<string | null>(() =>
    UserService.getTenantName(),
  );

  useEffect(() => {
    const syncTenantName = () => setTenantId(UserService.getTenantName());
    syncTenantName();
    window.addEventListener(
      UserService.TENANT_DISPLAY_NAME_UPDATED_EVENT,
      syncTenantName,
    );
    return () => {
      window.removeEventListener(
        UserService.TENANT_DISPLAY_NAME_UPDATED_EVENT,
        syncTenantName,
      );
    };
  }, []);

  let activeId = resolveActiveNavId(pathname);

  const catalog = buildSideNavCatalog({
    t,
    targetUris,
    mcpEnabled: Boolean(MCP_CONNECTION_ENABLED),
    natsMonitoringEnabled: Boolean(NATS_MONITORING_ENABLED),
  });

  const absorbExtensionItem = (uxElement: UiSchemaUxElement) => {
    const maybeActive = appendExtensionCatalogEntries(
      catalog,
      uxElement,
      pathname,
    );
    if (maybeActive) {
      activeId = maybeActive;
    }
  };
  ExtensionUxElementForDisplay({
    displayLocation: 'header_menu_item',
    elementCallback: absorbExtensionItem,
    extensionUxElements,
  });
  ExtensionUxElementForDisplay({
    displayLocation: 'primary_nav_item',
    elementCallback: absorbExtensionItem,
    extensionUxElements,
  });

  const reserveSecondaryPx = secondaryPanelHeightPx(catalog.length);
  const showTenantBadge = Boolean(tenantId) && !UserService.isSuperAdmin();
  const chromeMenus = useSideNavChromeMenus();

  const onNavClick = (entry: SideNavCatalogEntry) => {
    // Keep TreePanel when staying on Processes; clear it for every other destination.
    if (entry.id !== NAV_IDS.processes) {
      setAdditionalNavElement(null);
    }
  };

  const renderEntry = (entry: SideNavCatalogEntry) => {
    if (!canSeeNavEntry(entry, ability, permissionPlan)) {
      return null;
    }
    const selected = activeId === entry.id;
    return (
      <ListItem
        component={Link}
        to={entry.path}
        key={`${entry.id}-${entry.path}`}
        data-testid={`nav-item-${entry.id}`}
        onClick={() => onNavClick(entry)}
        sx={{
          bgcolor: selected ? 'background.light' : 'inherit',
          color: selected ? ACTIVE_ACCENT : 'inherit',
          borderColor: selected ? ACTIVE_ACCENT : 'transparent',
          borderLeftWidth: '4px',
          borderStyle: 'solid',
          justifyContent: railMode ? 'center' : 'flex-start',
        }}
      >
        <Tooltip title={railMode ? entry.label : ''} placement="right">
          <ListItemIcon
            sx={{ color: 'inherit', minWidth: railMode ? 24 : 40 }}
          >
            {iconForNavKey(entry.iconKey)}
          </ListItemIcon>
        </Tooltip>
        {railMode ? null : (
          <ListItemText
            primary={entry.label}
            data-testid={`nav-${entry.label.toLowerCase().replace(' ', '-')}`}
            primaryTypographyProps={{
              fontSize: '0.875rem',
              fontWeight: selected ? 'bold' : 'normal',
            }}
          />
        )}
      </ListItem>
    );
  };

  if (!permissionsLoaded) {
    return null;
  }

  return (
    <>
      <Stack
        sx={{
          ...DRAWER_SHELL_SX,
          width: railMode ? RAIL_WIDTH : EXPANDED_WIDTH,
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ p: 2, height: 'fit-content' }}
        >
          {railMode ? null : (
            <Stack alignItems="flex-start" sx={{ minWidth: 0, flexGrow: 1 }}>
              <MuiLink component={Link} to="/" data-testid="nav-logo-link">
                <SpiffLogo />
              </MuiLink>
              {showTenantBadge && tenantId ? (
                <SideNavTenantBadgeExpanded
                  tenantLabel={tenantId}
                  caption={t('tenant')}
                />
              ) : null}
            </Stack>
          )}
          <IconButton
            data-testid="nav-toggle-collapse-button"
            onClick={onToggleCollapse}
            sx={{ ml: railMode ? 'auto' : 0 }}
          >
            {narrowViewport ? (
              <CloseIcon />
            ) : (
              <CollapseGlyph
                collapsed={railMode}
                expandLabel={t('expand_navigation')}
                collapseLabel={t('collapse_navigation')}
              />
            )}
          </IconButton>
        </Stack>

        <GlobalTenantSelector isCollapsed={railMode} />
        {railMode && showTenantBadge && tenantId ? (
          <SideNavTenantBadgeCollapsed
            tenantLabel={tenantId}
            caption={t('tenant')}
          />
        ) : null}
        <Divider sx={{ mx: 2, mb: 1 }} />

        <List>{catalog.map(renderEntry)}</List>

        {railMode ? null : (
          <Box
            sx={{
              width: '100%',
              height: `calc(100vh - ${reserveSecondaryPx}px)`,
            }}
          >
            {additionalNavElement}
          </Box>
        )}

        <SideNavBottomFoot
          railMode={railMode}
          dark={isDark}
          onDarkToggle={onToggleDarkMode}
          onToggleProfile={chromeMenus.toggleProfile}
          onToggleLanguage={chromeMenus.toggleLanguage}
        />
      </Stack>
      <SideNavBottomOverlays
        railMode={railMode}
        profileOpen={chromeMenus.profileOpen}
        languageOpen={chromeMenus.languageOpen}
        tenantLabel={tenantId}
        extensionUxElements={extensionUxElements}
        onCloseLanguage={chromeMenus.closeLanguage}
      />
    </>
  );
}

export default SideNav;
