/**
 * App-shell chrome: theme, nav collapse, route fade, and mobile drawer visibility.
 */
import {
  PaletteMode,
  Theme,
  createTheme,
  useMediaQuery,
} from '@mui/material';
import {
  ReactElement,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { Location } from 'react-router-dom';
import { createSpiffTheme } from '@spiffworkflow-frontend/assets/theme/SpiffTheme';

export const ROUTE_FADE_IN = 'fadeIn';
export const ROUTE_FADE_OUT = 'fadeOutImmediate';

const NAV_COLLAPSE_STORAGE_KEY = 'isNavCollapsed';
const THEME_STORAGE_KEY = 'theme';

function readStoredTheme(): PaletteMode {
  return (localStorage.getItem(THEME_STORAGE_KEY) || 'light') as PaletteMode;
}

function readNavCollapsed(): boolean {
  const raw = localStorage.getItem(NAV_COLLAPSE_STORAGE_KEY);
  return raw ? JSON.parse(raw) : false;
}

export type AppShellChrome = {
  globalTheme: Theme;
  isDark: boolean;
  flipColorScheme: () => void;
  isNavCollapsed: boolean;
  isSideNavVisible: boolean;
  isMobile: boolean;
  openMobileNav: () => void;
  handleNavToggle: () => void;
  transitionStage: string;
  onRouteFadeEnd: (animationName: string) => void;
  additionalNavElement: ReactElement | null;
  setAdditionalNavElement: Dispatch<SetStateAction<ReactElement | null>>;
};

export function useAppShellChrome(location: Location): AppShellChrome {
  const [globalTheme, setGlobalTheme] = useState(() =>
    createTheme(createSpiffTheme(readStoredTheme())),
  );
  const isDark = globalTheme.palette.mode === 'dark';

  const [displayLocation, setDisplayLocation] = useState(location);
  const [transitionStage, setTransitionStage] = useState(ROUTE_FADE_IN);
  const [additionalNavElement, setAdditionalNavElement] =
    useState<ReactElement | null>(null);

  const [isNavCollapsed, setIsNavCollapsed] = useState(readNavCollapsed);
  const isMobile = useMediaQuery((theme: Theme) => theme.breakpoints.down('sm'));
  const [isSideNavVisible, setIsSideNavVisible] = useState(() => !isMobile);

  useEffect(() => {
    if (location !== displayLocation) {
      setTransitionStage(ROUTE_FADE_OUT);
    }
    if (transitionStage === ROUTE_FADE_OUT) {
      setDisplayLocation(location);
      setTransitionStage(ROUTE_FADE_IN);
    }
  }, [location, displayLocation, transitionStage]);

  useEffect(() => {
    setIsSideNavVisible(!isMobile);
  }, [isMobile]);

  const flipColorScheme = () => {
    const next: PaletteMode = isDark ? 'light' : 'dark';
    setGlobalTheme(createTheme(createSpiffTheme(next)));
    localStorage.setItem(THEME_STORAGE_KEY, next);
  };

  const handleNavToggle = () => {
    if (isMobile) {
      setIsSideNavVisible((visible) => !visible);
      return;
    }
    setIsNavCollapsed((collapsed) => {
      const next = !collapsed;
      localStorage.setItem(NAV_COLLAPSE_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const openMobileNav = () => {
    setIsSideNavVisible(true);
    setIsNavCollapsed(false);
  };

  const onRouteFadeEnd = (animationName: string) => {
    if (animationName !== ROUTE_FADE_OUT) {
      return;
    }
    setDisplayLocation(location);
    setTransitionStage(ROUTE_FADE_IN);
  };

  return {
    globalTheme,
    isDark,
    flipColorScheme,
    isNavCollapsed,
    isSideNavVisible,
    isMobile,
    openMobileNav,
    handleNavToggle,
    transitionStage,
    onRouteFadeEnd,
    additionalNavElement,
    setAdditionalNavElement,
  };
}
