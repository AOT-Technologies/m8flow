/**
 * Manual active-state CSS for nav items SideNav does not highlight itself.
 */
import { Theme } from '@mui/material';

type PathMatchMode = 'exact' | 'prefix';

type HighlightSpec = {
  hrefSuffix: string;
  mode: PathMatchMode;
};

const NAV_HIGHLIGHT_SPECS: HighlightSpec[] = [
  { hrefSuffix: '/tenants', mode: 'exact' },
  { hrefSuffix: '/tenant-management', mode: 'exact' },
  { hrefSuffix: '/connectors', mode: 'prefix' },
  { hrefSuffix: '/mcp-connection', mode: 'prefix' },
];

function pathMatches(pathname: string, spec: HighlightSpec): boolean {
  if (spec.mode === 'exact') {
    return pathname === spec.hrefSuffix;
  }
  return pathname.startsWith(spec.hrefSuffix);
}

function highlightCss(hrefSuffix: string, theme: Theme): string {
  const lightBg =
    (theme.palette as { background?: { light?: string } }).background?.light ||
    '#e3f2fd';
  const accent = theme.palette.primary.main;
  return `
    a[href$="${hrefSuffix}"] {
      background-color: ${lightBg} !important;
      color: ${accent} !important;
      border-left-width: 4px !important;
      border-style: solid !important;
      border-color: ${accent} !important;
    }
    a[href$="${hrefSuffix}"] .MuiListItemIcon-root {
      color: ${accent} !important;
    }
    a[href$="${hrefSuffix}"] .MuiTypography-root {
      font-weight: bold !important;
    }
  `;
}

export function NavActiveHighlightStyles({
  pathname,
  theme,
}: {
  pathname: string;
  theme: Theme;
}) {
  const activeSpecs = NAV_HIGHLIGHT_SPECS.filter((spec) =>
    pathMatches(pathname, spec),
  );

  return (
    <>
      {activeSpecs.map((spec) => (
        <style key={spec.hrefSuffix}>{highlightCss(spec.hrefSuffix, theme)}</style>
      ))}
    </>
  );
}
