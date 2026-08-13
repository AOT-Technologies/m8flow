/**
 * Drawer foot controls plus floating profile / language panels.
 * Markup and style objects are intentionally not line-aligned with upstream SideNav.
 */
import {
  useEffect,
  useState,
  type MouseEventHandler,
  type ReactElement,
} from 'react';
import {
  ButtonBase,
  IconButton,
  Link as MuiLink,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Brightness4,
  Brightness7,
  Flag,
  Logout,
  Person,
} from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DARK_MODE_ENABLED } from '@spiffworkflow-frontend/config';
import SpiffTooltip from '@spiffworkflow-frontend/components/SpiffTooltip';
import ExtensionUxElementForDisplay from '@spiffworkflow-frontend/components/ExtensionUxElementForDisplay';
import type { UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import UserService from '../services/UserService';

type ChromeProps = {
  railMode: boolean;
  dark: boolean;
  onDarkToggle: MouseEventHandler<HTMLButtonElement>;
  tenantLabel: string | null;
  extensionUxElements?: UiSchemaUxElement[] | null;
};

const FOOT_ANCHOR_SX = {
  position: 'absolute' as const,
  bottom: 16,
};

const PROFILE_SHEET_SX = {
  position: 'fixed' as const,
  width: 256,
  p: 2,
  zIndex: 1300,
  bgcolor: 'background.paper',
  right: 'auto' as const,
};

const LANGUAGE_SHEET_SX = {
  position: 'fixed' as const,
  width: 128,
  p: 2,
  zIndex: 1300,
  bgcolor: 'background.paper',
  right: 'auto' as const,
};

function profileExtensionLink(uxElement: UiSchemaUxElement): ReactElement {
  const href = `/extensions${uxElement.page}`;
  return (
    <Stack component="span" sx={{ mt: 1 }}>
      <MuiLink component={Link} to={href}>
        {uxElement.label}
      </MuiLink>
    </Stack>
  );
}

function SignOutRow({ label }: { label: string }) {
  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      <hr />
      <ButtonBase
        data-testid="sign-out-button"
        onClick={() => UserService.doLogout()}
        sx={{
          justifyContent: 'flex-start',
          gap: 1,
          color: 'inherit',
          font: 'inherit',
          width: '100%',
        }}
      >
        <Logout fontSize="small" />
        {label}
      </ButtonBase>
    </Stack>
  );
}

/** Shared open-state + dismiss handlers for foot buttons and floating sheets. */
export function useSideNavChromeMenus() {
  const [profileOpen, setProfileOpen] = useState(false);
  const [languageOpen, setLanguageOpen] = useState(false);

  useEffect(() => {
    const dismissFloating = (event: MouseEvent) => {
      const node = event.target as HTMLElement | null;
      if (!node) return;
      const awayFromProfile =
        !node.closest('.user-profile') && !node.closest('.person-icon');
      const awayFromLanguage =
        !node.closest('.language-menu') && !node.closest('.language-icon');
      if (awayFromProfile) setProfileOpen(false);
      if (awayFromLanguage) setLanguageOpen(false);
    };
    window.addEventListener('click', dismissFloating);
    return () => window.removeEventListener('click', dismissFloating);
  }, []);

  return {
    profileOpen,
    languageOpen,
    toggleProfile: () => setProfileOpen((v) => !v),
    toggleLanguage: () => setLanguageOpen((v) => !v),
    closeLanguage: () => setLanguageOpen(false),
  };
}

type FootProps = Pick<ChromeProps, 'railMode' | 'dark' | 'onDarkToggle'> & {
  onToggleProfile: () => void;
  onToggleLanguage: () => void;
};

/** Foot controls stay inside the drawer shell. */
export function SideNavBottomFoot({
  railMode,
  dark,
  onDarkToggle,
  onToggleProfile,
  onToggleLanguage,
}: FootProps) {
  const { t } = useTranslation();
  const tipSide = railMode ? 'right' : 'top';

  return (
    <Stack
      direction={railMode ? 'column' : 'row'}
      alignItems="center"
      spacing={railMode ? 0 : 1}
      sx={{
        ...FOOT_ANCHOR_SX,
        left: railMode ? '50%' : 16,
        transform: railMode ? 'translateX(-50%)' : undefined,
      }}
    >
      <SpiffTooltip title={t('user_actions')} placement={tipSide}>
        <IconButton
          data-testid="nav-user-actions-button"
          aria-label={t('user_actions')}
          onClick={onToggleProfile}
          className="person-icon"
        >
          <Person />
        </IconButton>
      </SpiffTooltip>
      {DARK_MODE_ENABLED ? (
        <SpiffTooltip title={t('toggle_dark_mode')} placement={tipSide}>
          <IconButton
            data-testid="nav-toggle-dark-mode-button"
            onClick={onDarkToggle}
          >
            {dark ? <Brightness7 /> : <Brightness4 />}
          </IconButton>
        </SpiffTooltip>
      ) : null}
      <SpiffTooltip title={t('language')} placement={tipSide}>
        <IconButton
          data-testid="nav-language-button"
          aria-label={t('language')}
          onClick={onToggleLanguage}
          className="language-icon"
        >
          <Flag />
        </IconButton>
      </SpiffTooltip>
    </Stack>
  );
}

type OverlayProps = {
  railMode: boolean;
  profileOpen: boolean;
  languageOpen: boolean;
  tenantLabel: string | null;
  extensionUxElements?: UiSchemaUxElement[] | null;
  onCloseLanguage: () => void;
};

/**
 * Floating sheets render as siblings of the drawer (not inside overflow:hidden)
 * so a collapsed rail does not clip them.
 */
export function SideNavBottomOverlays({
  railMode,
  profileOpen,
  languageOpen,
  tenantLabel,
  extensionUxElements,
  onCloseLanguage,
}: OverlayProps) {
  const { t, i18n } = useTranslation();
  const email = UserService.getUserEmail();
  const displayName = UserService.getPreferredUsername();

  return (
    <>
      {profileOpen ? (
        <Paper
          elevation={3}
          className="user-profile"
          data-testid="nav-user-profile-panel"
          sx={{
            ...PROFILE_SHEET_SX,
            // Clear the rail tooltip when the drawer is collapsed.
            bottom: railMode ? 100 : 60,
            left: 32,
          }}
        >
          <Tooltip title={displayName} placement="top" enterDelay={500}>
            <Typography
              variant="subtitle1"
              noWrap
              sx={{ fontWeight: 600 }}
              data-testid="nav-username"
            >
              {displayName}
            </Typography>
          </Tooltip>
          {displayName !== email ? (
            <Typography
              variant="body2"
              color="text.secondary"
              noWrap
              data-testid="nav-user-email"
            >
              {email}
            </Typography>
          ) : null}
          {tenantLabel ? (
            <Tooltip title={tenantLabel} placement="top" enterDelay={500}>
              <Typography
                variant="body2"
                noWrap
                data-testid="nav-tenant-id"
                sx={{ color: 'text.secondary', fontWeight: 600, mt: 0.5 }}
              >
                {tenantLabel}
              </Typography>
            </Tooltip>
          ) : null}
          <ExtensionUxElementForDisplay
            displayLocation="user_profile_item"
            elementCallback={profileExtensionLink}
            extensionUxElements={extensionUxElements}
          />
          {!UserService.authenticationDisabled() ? (
            <SignOutRow label={t('sign_out')} />
          ) : null}
        </Paper>
      ) : null}

      {languageOpen ? (
        <Paper
          elevation={3}
          className="language-menu"
          data-testid="nav-language-menu"
          sx={{
            ...LANGUAGE_SHEET_SX,
            bottom: railMode ? 80 : 60,
            left: railMode ? 32 : 96,
          }}
        >
          <Stack spacing={0.5}>
            {Object.keys(i18n.store.data)
              .sort()
              .map((code) => {
                const active = i18n.resolvedLanguage === code;
                return (
                  <MuiLink
                    key={code}
                    component="button"
                    data-testid={`nav-language-option-${code}`}
                    onClick={() => {
                      i18n.changeLanguage(code);
                      onCloseLanguage();
                    }}
                    sx={{
                      textAlign: 'left',
                      textDecoration: 'none',
                      color: 'inherit',
                      fontWeight: active ? 700 : 400,
                    }}
                  >
                    {code}
                  </MuiLink>
                );
              })}
          </Stack>
        </Paper>
      ) : null}
    </>
  );
}
