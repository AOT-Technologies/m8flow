import React, {
  useState,
  useEffect,
  ReactElement,
  MouseEventHandler,
} from "react";
import {
  Box,
  Typography,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip,
  Paper,
  Link as MuiLink,
  useMediaQuery,
  Chip,
} from "@mui/material";
import {
  Home,
  ChevronLeft,
  ChevronRight,
  Logout,
  Person,
  Brightness7,
  Brightness4,
  Close as CloseIcon,
  Schema,
  Timeline,
  Markunread,
  SettingsApplicationsSharp,
  Extension,
  Flag,
  Description,
} from "@mui/icons-material";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import appVersionInfo from "@spiffworkflow-frontend/helpers/appVersionInfo";
import {
  DARK_MODE_ENABLED,
  DOCUMENTATION_URL,
  SPIFF_ENVIRONMENT,
} from "@spiffworkflow-frontend/config";
import UserService from "../services/UserService";
import SpiffLogo from "./SpiffLogo";
import SpiffTooltip from "@spiffworkflow-frontend/components/SpiffTooltip";
import { UiSchemaUxElement } from "@spiffworkflow-frontend/extension_ui_schema_interfaces";
import ExtensionUxElementForDisplay from "@spiffworkflow-frontend/components/ExtensionUxElementForDisplay";
import { useM8flowUriListForPermissions as useUriListForPermissions } from "../hooks/M8flowUriListForPermissions";
import {
  PermissionsToCheck,
  NavItem,
} from "@spiffworkflow-frontend/interfaces";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";

const drawerWidth = 350;
const collapsedDrawerWidth = 64;
const mainBlue = "primary.main";

type OwnProps = {
  isCollapsed: boolean;
  onToggleCollapse: MouseEventHandler<HTMLButtonElement>;
  onToggleDarkMode: MouseEventHandler<HTMLButtonElement>;
  isDark: boolean;
  additionalNavElement?: ReactElement | null;
  setAdditionalNavElement: Function;
  extensionUxElements?: UiSchemaUxElement[] | null;
};

// Define an object to map route paths to identifiers
const routeIdentifiers = {
  HOME: "home",
  PROCESSES: "processes",
  PROCESS_INSTANCES: "processInstances",
  MESSAGES: "messages",
  CONFIGURATION: "configuration",
  TEMPLATES: "templates",
};

function SideNav({
  isCollapsed,
  onToggleCollapse,
  onToggleDarkMode,
  isDark,
  additionalNavElement,
  setAdditionalNavElement,
  extensionUxElements,
}: OwnProps) {
  const isMobile = useMediaQuery((theme: any) => theme.breakpoints.down("sm"));

  const location = useLocation();

  const { t, i18n } = useTranslation();

  const { targetUris } = useUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {
    [targetUris.messageInstanceListPath]: ["GET"],
    [targetUris.processGroupListPath]: ["GET"],
    [targetUris.processInstanceListPath]: ["GET"],
    [targetUris.processInstanceListForMePath]: ["POST"],
    [targetUris.secretListPath]: ["GET"],
    "/tasks/*": ["PUT"],
    "/m8flow/tenants": ["GET"],
    "/m8flow/templates": ["GET"],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );

  // Determine the selected tab based on the current route
  let selectedTab: string | null = null;
  if (location.pathname === "/" || location.pathname === "/started-by-me") {
    selectedTab = routeIdentifiers.HOME;
  } else if (location.pathname.startsWith("/process-instances")) {
    selectedTab = routeIdentifiers.PROCESS_INSTANCES;
  } else if (location.pathname.startsWith("/process-")) {
    selectedTab = routeIdentifiers.PROCESSES; // This might need further refinement
  } else if (location.pathname === "/messages") {
    selectedTab = routeIdentifiers.MESSAGES;
  } else if (location.pathname.startsWith("/configuration")) {
    selectedTab = routeIdentifiers.CONFIGURATION;
  } else if (location.pathname.startsWith("/templates")) {
    selectedTab = routeIdentifiers.TEMPLATES;
  }

  const versionInfo = appVersionInfo();
  let aboutLinkElement = null;
  if (Object.keys(versionInfo).length) {
    aboutLinkElement = (
      <MuiLink component={Link} to="/about">
        {t("about")}
      </MuiLink>
    );
  }
  const userEmail = UserService.getUserEmail();
  const username = UserService.getPreferredUsername();
  let externalDocumentationUrl = "https://spiff-arena.readthedocs.io";
  if (DOCUMENTATION_URL) {
    externalDocumentationUrl = DOCUMENTATION_URL;
  }

  // State for controlling the display of the user profile section
  const [showUserProfile, setShowUserProfile] = useState(false);
  const [showLanguageMenu, setShowLanguageMenu] = useState(false);

  const handlePersonIconClick = () => {
    setShowUserProfile(!showUserProfile);
  };

  const handleLanguageMenuClick = () => {
    setShowLanguageMenu(!showLanguageMenu);
  };

  // Close user profile section when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const element = event.target as HTMLElement;
      if (
        element &&
        !element.closest(".user-profile") &&
        !element.closest(".person-icon")
      ) {
        setShowUserProfile(false);
      }
      if (
        element &&
        !element.closest(".language-menu") &&
        !element.closest(".language-icon")
      ) {
        setShowLanguageMenu(false);
      }
    };

    window.addEventListener("click", handleClickOutside);

    return () => {
      window.removeEventListener("click", handleClickOutside);
    };
  }, []);

  const collapseOrExpandIcon = isCollapsed ? (
    <SpiffTooltip title={t("expand_navigation")} placement="right">
      <ChevronRight data-testid="expand-primary-nav" />
    </SpiffTooltip>
  ) : (
    <SpiffTooltip title={t("collapse_navigation")} placement="bottom">
      <ChevronLeft data-testid="collapse-primary-nav" />
    </SpiffTooltip>
  );

  const navItems: NavItem[] = [
    {
      text: t("home"),
      icon: <Home />,
      route: "/",
      id: routeIdentifiers.HOME,
      permissionRoutes: ["/tasks/*"],
    },
    {
      text: t("processes"),
      icon: <Schema />,
      route: "/process-groups",
      id: routeIdentifiers.PROCESSES,
      permissionRoutes: [targetUris.processGroupListPath],
    },
    {
      text: t("process_instances"),
      icon: <Timeline />,
      route: "/process-instances",
      id: routeIdentifiers.PROCESS_INSTANCES,
      permissionRoutes: [targetUris.processInstanceListPath],
    },
    {
      text: t("messages"),
      icon: <Markunread />,
      route: "/messages",
      id: routeIdentifiers.MESSAGES,
      permissionRoutes: [targetUris.messageInstanceListPath],
    },
    {
      text: t("configuration"),
      icon: <SettingsApplicationsSharp />,
      route: "/configuration",
      id: routeIdentifiers.CONFIGURATION,
      permissionRoutes: [
        targetUris.secretListPath,
      ],
    },
    {
      text: "Templates",
      icon: <Description />,
      route: "/templates",
      id: routeIdentifiers.TEMPLATES,
      permissionRoutes: ["/m8flow/templates"],
    },
  ];

  const extensionHeaderMenuItemElement = (uxElement: UiSchemaUxElement) => {
    const navItemPage = `/extensions${uxElement.page}`;
    if (location.pathname === navItemPage) {
      selectedTab = uxElement.page;
    }
    navItems.push({
      text: uxElement.label,
      icon: <Extension />,
      route: navItemPage,
      id: uxElement.page,
    });
  };
  ExtensionUxElementForDisplay({
    displayLocation: "header_menu_item",
    elementCallback: extensionHeaderMenuItemElement,
    extensionUxElements,
  });
  ExtensionUxElementForDisplay({
    displayLocation: "primary_nav_item",
    elementCallback: extensionHeaderMenuItemElement,
    extensionUxElements,
  });

  const visibleNavItems = navItems;

  // 45 * number of nav items like "HOME" and "PROCESS INSTANCES" plus 140
  const pixelsToRemoveFromAdditionalElement = 45 * visibleNavItems.length + 140;

  const extensionUserProfileElement = (uxElement: UiSchemaUxElement) => {
    const navItemPage = `/extensions${uxElement.page}`;
    return (
      <>
        <br />
        <MuiLink component={Link} to={navItemPage}>
          {uxElement.label}
        </MuiLink>
      </>
    );
  };

  const checkUserHasAccessToNavItem = (item: NavItem) => {
    if (!("permissionRoutes" in item)) {
      return true;
    }

    let hasPermission = false;
    item.permissionRoutes?.forEach((targetUri: string) => {
      let method = "GET";
      // if the uri is in the permissionRequestData then use the first action listed
      if (targetUri in permissionRequestData) {
        [method] = permissionRequestData[targetUri];
      }
      if (ability.can(method, targetUri)) {
        hasPermission = true;
      }
    });
    return hasPermission;
  };

  if (permissionsLoaded) {
    return (
      <>
        <Box
          sx={{
            width: isCollapsed ? collapsedDrawerWidth : drawerWidth,
            flexShrink: 0,
            borderRight: "1px solid #e0e0e0",
            height: "100vh",
            bgcolor: "background.nav",
            transition: "width 0.3s",
            overflow: "hidden",
            position: "relative",
          }}
        >
          <Box
            sx={{
              p: 2,
              height: 64,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            {!isCollapsed && (
              <Typography
                variant="h6"
                color={mainBlue}
                sx={{
                  fontWeight: "bold",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <MuiLink component={Link} to="/" data-testid="nav-logo-link">
                  <SpiffLogo />
                </MuiLink>
              </Typography>
            )}
            <IconButton
              data-testid="nav-toggle-collapse-button"
              onClick={(event) => {
                onToggleCollapse(event);
              }}
              sx={{ ml: isCollapsed ? "auto" : 0 }}
            >
              {isMobile ? <CloseIcon /> : collapseOrExpandIcon}
            </IconButton>
          </Box>
          <List>
            {visibleNavItems.map((item) => {
              if (checkUserHasAccessToNavItem(item)) {
                return (
                  <ListItem
                    component={Link}
                    to={item.route}
                    key={item.text}
                    data-testid={`nav-item-${item.id}`}
                    onClick={() => {
                      // additionalNavElement is the TreePanel in this case so do not
                      // remove it when you are navigating to the processes page from the processes page
                      if (item.id !== routeIdentifiers.PROCESSES) {
                        setAdditionalNavElement(null);
                      }
                    }}
                    sx={{
                      bgcolor:
                        selectedTab === item.id
                          ? "background.light"
                          : "inherit",
                      color: selectedTab === item.id ? mainBlue : "inherit",
                      borderColor:
                        selectedTab === item.id ? mainBlue : "transparent",
                      borderLeftWidth: "4px",
                      borderStyle: "solid",
                      justifyContent: isCollapsed ? "center" : "flex-start",
                    }}
                  >
                    <Tooltip
                      title={isCollapsed ? item.text : ""}
                      placement="right"
                    >
                      <ListItemIcon
                        sx={{
                          color: "inherit",
                          minWidth: isCollapsed ? 24 : 40,
                        }}
                      >
                        {item.icon}
                      </ListItemIcon>
                    </Tooltip>
                    {!isCollapsed && (
                      <ListItemText
                        primary={item.text}
                        data-testid={`nav-${item.text.toLowerCase().replace(" ", "-")}`}
                        primaryTypographyProps={{
                          fontSize: "0.875rem",
                          fontWeight:
                            selectedTab === item.id ? "bold" : "normal",
                        }}
                      />
                    )}
                  </ListItem>
                );
              }
              return null;
            })}
          </List>
          {!isCollapsed && (
            <Box
              sx={{
                width: "100%",
                height: `calc(100vh - ${pixelsToRemoveFromAdditionalElement}px)`,
              }}
            >
              {additionalNavElement}
            </Box>
          )}
          <Box
            sx={{
              position: "absolute",
              bottom: 16,
              left: isCollapsed ? "50%" : 16,
              transform: isCollapsed ? "translateX(-50%)" : "none",
              alignItems: "center", // Vertically center items
              display: "flex",
              flexDirection: isCollapsed ? "column" : "row",
              gap: isCollapsed ? 0 : 1,
            }}
          >
            <SpiffTooltip
              title={t("user_actions")}
              placement={isCollapsed ? "right" : "top"}
            >
              <IconButton
                data-testid="nav-user-actions-button"
                aria-label={t("user_actions")}
                onClick={handlePersonIconClick}
                className="person-icon"
              >
                <Person />
              </IconButton>
            </SpiffTooltip>
            {DARK_MODE_ENABLED ? (
              <SpiffTooltip
                title={t("toggle_dark_mode")}
                placement={isCollapsed ? "right" : "top"}
              >
                <IconButton data-testid="nav-toggle-dark-mode-button" onClick={onToggleDarkMode}>
                  {isDark ? <Brightness7 /> : <Brightness4 />}
                </IconButton>
              </SpiffTooltip>
            ) : null}
            <SpiffTooltip
              title={t("language")}
              placement={isCollapsed ? "right" : "top"}
            >
              <IconButton
                data-testid="nav-language-button"
                aria-label={t("language")}
                onClick={handleLanguageMenuClick}
                className="language-icon"
              >
                <Flag />
              </IconButton>
            </SpiffTooltip>
            {/* {SPIFF_ENVIRONMENT && (
              <SpiffTooltip
                title={t("environment")}
                placement={isCollapsed ? "right" : "top"}
              >
                <Box sx={{ display: "flex", alignItems: "center" }}>
                  <Chip
                    label={SPIFF_ENVIRONMENT}
                    color="primary"
                    size="small"
                    sx={{
                      cursor: "default",
                    }}
                  />
                </Box>
              </SpiffTooltip>
            )} */}
          </Box>
        </Box>
        {showUserProfile && (
          <Paper
            elevation={3}
            className="user-profile"
            data-testid="nav-user-profile-panel"
            sx={{
              position: "fixed",
              bottom: isCollapsed ? 100 : 60, // if it's collapsed, make it a little higher so it doesn't overlap with the tooltip to the right of the icon
              left: 32,
              right: "auto",
              width: 256,
              padding: 2,
              zIndex: 1300,
              bgcolor: "background.paper",
            }}
          >
            <Typography variant="subtitle1">{username}</Typography>
            {username !== userEmail && (
              <Typography variant="body2">{userEmail}</Typography>
            )}
            {/* <hr />
            {aboutLinkElement}
            <br />
            <MuiLink
              component="a"
              href={externalDocumentationUrl}
              target="_blank"
              rel="noreferrer"
            >
              {t("documentation")}
            </MuiLink> */}
            <ExtensionUxElementForDisplay
              displayLocation="user_profile_item"
              elementCallback={extensionUserProfileElement}
              extensionUxElements={extensionUxElements}
            />
            {!UserService.authenticationDisabled() && (
              <>
                <hr />
                <MuiLink
                  component="button"
                  data-testid="sign-out-button"
                  onClick={() => UserService.doLogout()}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <Logout />
                  &nbsp;&nbsp;{t("sign_out")}
                </MuiLink>
              </>
            )}
          </Paper>
        )}
        {showLanguageMenu && (
          <Paper
            elevation={3}
            className="language-menu"
            data-testid="nav-language-menu"
            sx={{
              position: "fixed",
              bottom: isCollapsed ? 80 : 60, // if it's collapsed, make it a little higher so it doesn't overlap with the tooltip to the right of the icon
              left: isCollapsed ? 32 : 96,
              right: "auto",
              width: 128,
              padding: 2,
              zIndex: 1300,
              bgcolor: "background.paper",
            }}
          >
            {Object.keys(i18n.store.data)
              .sort()
              .map((language) => (
                <MuiLink
                  key={language}
                  component="button"
                  data-testid={`nav-language-option-${language}`}
                  onClick={() => {
                    i18n.changeLanguage(language);
                    setShowLanguageMenu(false);
                  }}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    textDecoration: "none",
                    color: "inherit",
                    fontWeight:
                      i18n.resolvedLanguage === language ? "bold" : "unset",
                  }}
                >
                  {language}
                </MuiLink>
              ))}
          </Paper>
        )}
      </>
    );
  }
  return null;
}

export default SideNav;
