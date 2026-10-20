import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
  type SVGProps,
} from 'react';
import {
  Activity,
  Building2,
  ChevronDown,
  ClipboardCheck,
  Flag,
  GitBranch,
  Home,
  Link2,
  ListFilter,
  LogOut,
  Mail,
  Moon,
  Server,
  Sun,
  User,
  Users,
  Wrench,
} from 'lucide-react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';
import { NavLink, useInRouterContext, useLocation } from 'react-router-dom';

import { LOCALE_OPTIONS } from '@/i18n';
import { cn } from '@/lib/utils';
import type { OrganizationMembership } from '@/lib/auth';

// Radix Select/DropdownMenu (and their positioning code) only serve super-admins and
// multi-organisation users, so they load on demand instead of with the first page.
const SuperAdminTenantSelect = lazy(() =>
  import('./SuperAdminTenantSelect').then((module) => ({ default: module.SuperAdminTenantSelect })),
);
const TenantSwitcher = lazy(() => import('./TenantSwitcher').then((module) => ({ default: module.TenantSwitcher })));

/**
 * Suspense plus an error boundary for those pickers: if a chunk fails to load (offline, or a
 * deploy replaced it), the read-only stand-in stays instead of the error taking down the app.
 */
class LazyPicker extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    const { fallback, children } = this.props;
    return this.state.failed ? fallback : <Suspense fallback={fallback}>{children}</Suspense>;
  }
}

export type SidebarTenant = {
  id: string;
  name: string;
};

export type LiveNavId =
  | 'home'
  | 'tenants'
  | 'tenant-management'
  | 'processes'
  | 'process-instances'
  | 'task-review'
  | 'messages'
  | 'mcp'
  | 'mcp-tools';

export type SidebarProps = {
  showProcesses?: boolean;
  showProcessInstances?: boolean;
  showTaskReview?: boolean;
  showSystem?: boolean;
  /** When true, show the Tenant selector (ticket 02: super-admin only). */
  showTenantSelector?: boolean;
  tenants?: SidebarTenant[];
  /** `null` means "All Tenants". Ignored when showTenantSelector is false. */
  selectedTenantId?: string | null;
  onTenantChange?: (tenantId: string | null) => void;
  /**
   * Read-only active-tenant chip for non-super-admin shared-realm users.
   * Ignored when `showTenantSelector` is true. Becomes an interactive
   * switcher instead when `organizations` has >=2 entries (ticket 06).
   */
  activeTenantLabel?: string | null;
  /**
   * The user's shared-realm org memberships. When this has >=2 entries and
   * `showTenantSelector` is false, nav-tenant-name renders as a TenantSwitcher
   * instead of the read-only chip. A single (or empty) list keeps the chip.
   */
  organizations?: OrganizationMembership[];
  /** When set, Profile opens a menu with Log out (and optional user label). */
  onLogout?: () => void;
  /** Display name shown in the Profile menu (username / email). */
  userLabel?: string | null;
  /**
   * Which live nav item looks selected when rendered outside a router
   * (prototypes). Ignored when a React Router context is present.
   */
  activeNavId?: LiveNavId | null;
  /** Setup → Configuration live link when the user has YAML secrets read. */
  showConfiguration?: boolean;
  /** Setup → Connectors live link when the user has YAML connectors-grouped read. */
  showConnectors?: boolean;
  /** Show Setup when at least one Setup module is permitted. */
  showSetup?: boolean;
  /** Setup → Templates link when the backend grants template read access. */
  showTemplates?: boolean;
  /** Setup → API Keys link when the backend grants NATS API key read access. */
  showApiKeys?: boolean;
  /** Show MCP Connection when its backend read permission is granted. */
  showMcpConnection?: boolean;
  /** Show MCP Tools when the backend grants catalog read (`/m8flow/mcp-tools` GET). */
  showMcpTools?: boolean;
  /** Show Messages when its backend read permission is granted. */
  showMessages?: boolean;
  /** Browser URL for the Celery/Flower monitoring dashboard. */
  celeryMonitoringUrl?: string;
  /** Show the in-app NATS monitor (`/system/nats`) when its backend read permission is granted. */
  showNatsMonitoring?: boolean;
  /** Super-admin: Tenants nav is a live `/tenants` link. Hidden otherwise. */
  showTenantsNav?: boolean;
  /** Tenant-admin: Tenant Management is a live `/tenant-management` link. Hidden for super-admin (they enter via Tenants). */
  showTenantManagement?: boolean;
  className?: string;
};

type LucideIcon = ComponentType<SVGProps<SVGSVGElement> & { className?: string }>;

type NavItem = {
  id: string;
  labelKey: ParseKeys;
  icon: LucideIcon;
  /** Route path when this item is a live link. */
  to?: string;
  live?: boolean;
};

const TOP_NAV: NavItem[] = [
  { id: 'home', labelKey: 'shell.nav.home', icon: Home, to: '/', live: true },
  { id: 'tenants', labelKey: 'shell.nav.tenants', icon: Building2, to: '/tenants', live: true },
  {
    id: 'tenant-management',
    labelKey: 'shell.nav.tenantManagement',
    icon: Users,
    to: '/tenant-management',
    live: true,
  },
  { id: 'processes', labelKey: 'shell.nav.processes', icon: GitBranch, to: '/processes', live: true },
  {
    id: 'process-instances',
    labelKey: 'shell.nav.processInstances',
    icon: Activity,
    to: '/process-instances',
    live: true,
  },
  { id: 'task-review', labelKey: 'shell.nav.taskReview', icon: ClipboardCheck, to: '/task-review', live: true },
  { id: 'messages', labelKey: 'shell.nav.messages', icon: Mail, to: '/messages', live: true },
  { id: 'mcp', labelKey: 'shell.nav.mcpConnection', icon: Link2, to: '/mcp-connection', live: true },
  { id: 'mcp-tools', labelKey: 'shell.nav.mcpTools', icon: Wrench, to: '/mcp-tools', live: true },
];

type SidebarChild = {
  labelKey: ParseKeys;
  /** Route path when this child is a live link (Templates modeler map, ticket 02). */
  to?: string;
  external?: boolean;
};

const SETUP_CHILDREN: SidebarChild[] = [
  { labelKey: 'shell.nav.configuration' },
  { labelKey: 'shell.nav.connectors' },
  { labelKey: 'shell.nav.templates', to: '/templates' },
];
const CONFIGURATION_CHILD: SidebarChild = {
  labelKey: 'shell.nav.configuration',
  to: '/configuration/secrets',
};
const CONNECTORS_CHILD: SidebarChild = {
  labelKey: 'shell.nav.connectors',
  to: '/connectors',
};
const API_KEYS_CHILD: SidebarChild = {
  labelKey: 'shell.nav.apiKeys',
  to: '/api-keys',
};
const THEME_STORAGE_KEY = 'm8flow_theme';

type Theme = 'light' | 'dark';

function readTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
}

function systemChildren(celeryMonitoringUrl: string, showNatsMonitoring: boolean): SidebarChild[] {
  const children: Array<SidebarChild | null> = [
    celeryMonitoringUrl ? { labelKey: 'shell.nav.celery', to: celeryMonitoringUrl, external: true } : null,
    showNatsMonitoring ? { labelKey: 'shell.nav.nats', to: '/system/nats' } : null,
  ];
  return children.filter((child): child is SidebarChild => child !== null);
}

function activeNavIdFromPath(pathname: string, showTenantsNav = false): LiveNavId | null {
  if (pathname === '/' || pathname === '') {
    return 'home';
  }
  if (pathname === '/tenants' || pathname.startsWith('/tenants/')) {
    return 'tenants';
  }
  if (pathname === '/tenant-management' || pathname.startsWith('/tenant-management/')) {
    // Super-admin reaches tenant admin from the registry; keep Tenants selected.
    return showTenantsNav ? 'tenants' : 'tenant-management';
  }
  if (pathname === '/processes' || pathname.startsWith('/processes/')) {
    return 'processes';
  }
  if (pathname === '/process-instances' || pathname.startsWith('/process-instances/')) {
    return 'process-instances';
  }
  if (pathname === '/task-review' || pathname.startsWith('/task-review/')) {
    return 'task-review';
  }
  if (pathname === '/messages' || pathname.startsWith('/messages/')) {
    return 'messages';
  }
  if (pathname === '/mcp-connection' || pathname.startsWith('/mcp-connection/')) {
    return 'mcp';
  }
  if (pathname === '/mcp-tools' || pathname.startsWith('/mcp-tools/')) {
    return 'mcp-tools';
  }
  return null;
}

/**
 * App sidebar matching `m8flow Home copy.html`. Home, Processes, and (for
 * super-admin) Tenants are live routes when a React Router context is
 * present. Tenants is omitted unless `showTenantsNav` is set. Other items
 * stay visually present at full opacity but inert — no route, no click
 * handler — rather than `disabled`/greyed, which would read as a permission
 * denial. Collapsible Setup/System groups still expand/collapse (chrome, not
 * navigation). Profile opens a small popout for Log out when `onLogout` is
 * provided.
 */
export function Sidebar(props: SidebarProps) {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <SidebarInRouter {...props} />;
  }
  return <SidebarView {...props} activeNavId={props.activeNavId ?? 'home'} linkLiveNav={false} />;
}

function SidebarInRouter(props: SidebarProps) {
  const { pathname } = useLocation();
  return (
    <SidebarView
      {...props}
      activeNavId={activeNavIdFromPath(pathname, props.showTenantsNav)}
      linkLiveNav
    />
  );
}

function SidebarView({
  showProcesses = true,
  showProcessInstances = true,
  showTaskReview = true,
  showSystem = false,
  showTenantSelector = false,
  tenants = [],
  selectedTenantId = null,
  onTenantChange,
  onLogout,
  userLabel = null,
  activeNavId = 'home',
  linkLiveNav = false,
  showConfiguration = false,
  showConnectors = false,
  showSetup = true,
  showTemplates = true,
  showApiKeys = false,
  showMcpConnection = true,
  showMcpTools = false,
  showMessages = true,
  celeryMonitoringUrl = '',
  showNatsMonitoring = false,
  showTenantsNav = false,
  showTenantManagement = false,
  activeTenantLabel = null,
  organizations = [],
  className,
}: SidebarProps & { linkLiveNav?: boolean }) {
  const { t } = useTranslation();
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [setupOpen, setSetupOpen] = useState(true);
  const [systemOpen, setSystemOpen] = useState(true);
  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Ignore unavailable storage; the current page can still be themed.
    }
  }, [theme]);

  const monitoringChildren = systemChildren(celeryMonitoringUrl, showNatsMonitoring);
  const setupChildren = [
    ...(showConfiguration ? [CONFIGURATION_CHILD] : []),
    showConnectors ? CONNECTORS_CHILD : SETUP_CHILDREN[1],
    ...(showTemplates ? [SETUP_CHILDREN[2]] : []),
    ...(showApiKeys ? [API_KEYS_CHILD] : []),
  ];

  const topNav = TOP_NAV.filter((item) => {
    if (item.id === 'processes') return showProcesses;
    if (item.id === 'process-instances') return showProcessInstances;
    if (item.id === 'task-review') return showTaskReview;
    if (item.id === 'mcp') return showMcpConnection;
    if (item.id === 'mcp-tools') return showMcpTools;
    if (item.id === 'messages') return showMessages;
    if (item.id === 'tenants') {
      return showTenantsNav;
    }
    if (item.id === 'tenant-management') {
      return showTenantManagement;
    }
    return true;
  });

  return (
    <aside
      className={cn(
        'sticky top-0 flex h-screen w-[264px] shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground',
        className,
      )}
    >
      <div className="px-6 pb-4 pt-6">
        <div className="text-[26px] font-bold tracking-tight text-foreground">
          m8<span className="text-primary">flow</span>
        </div>
      </div>

      {showTenantSelector ? (
        <div className="px-6 pb-4">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
            <Building2 className="size-3" aria-hidden />
            {t('shell.tenant.label')}
          </div>
          <LazyPicker
            fallback={
              <div className="flex h-9 items-center rounded-lg border border-input bg-sidebar px-2.5 text-sm text-foreground">
                {tenants.find((tenant) => tenant.id === selectedTenantId)?.name ?? t('shell.tenant.allTenants')}
              </div>
            }
          >
            <SuperAdminTenantSelect
              tenants={tenants}
              selectedTenantId={selectedTenantId}
              onTenantChange={onTenantChange}
            />
          </LazyPicker>
        </div>
      ) : activeTenantLabel && organizations.length >= 2 ? (
        <LazyPicker fallback={<TenantChip label={activeTenantLabel} />}>
          <TenantSwitcher activeTenantLabel={activeTenantLabel} organizations={organizations} />
        </LazyPicker>
      ) : activeTenantLabel ? (
        <TenantChip label={activeTenantLabel} />
      ) : null}

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 pb-3">
        {topNav.map((item) => (
          <NavRow
            key={item.id}
            item={item}
            active={activeNavId === item.id}
            linkLiveNav={linkLiveNav}
          />
        ))}

        <div className="mx-3 my-2 h-px bg-border" />

        {showSetup && <CollapsibleGroup
          label={t('shell.nav.setup')}
          icon={ListFilter}
          open={setupOpen}
          onToggle={() => setSetupOpen((open) => !open)}
        >
          {setupChildren.map((child) =>
            child.to && linkLiveNav ? (
              <LiveChild key={child.labelKey} label={t(child.labelKey)} to={child.to} />
            ) : (
              <InertChild key={child.labelKey} label={t(child.labelKey)} />
            ),
          )}
        </CollapsibleGroup>}

        {showSystem && monitoringChildren.length > 0 && <CollapsibleGroup
          label={t('shell.nav.system')}
          icon={Server}
          open={systemOpen}
          onToggle={() => setSystemOpen((open) => !open)}
        >
          {monitoringChildren.map((child) => (
            child.external && child.to ? (
              <ExternalChild key={child.labelKey} label={t(child.labelKey)} href={child.to} />
            ) : child.to && linkLiveNav ? (
              <LiveChild key={child.labelKey} label={t(child.labelKey)} to={child.to} />
            ) : (
              <InertChild key={child.labelKey} label={t(child.labelKey)} />
            )
          ))}
        </CollapsibleGroup>}
      </nav>

      <div className="flex items-center gap-4 border-t border-border px-6 py-4 text-muted-foreground">
        {onLogout ? (
          <ProfileMenu userLabel={userLabel} onLogout={onLogout} />
        ) : (
          <FooterIcon icon={User} label={t('shell.profile.label')} />
        )}
        <ThemeToggle theme={theme} onToggle={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} />
        <LocaleMenu />
      </div>
    </aside>
  );
}

/** Read-only active-tenant chip; also stands in for TenantSwitcher while it loads. */
function TenantChip({ label }: { label: string }) {
  const { t } = useTranslation();
  return (
    <div className="px-6 pb-4">
      <div
        data-testid="nav-tenant-name"
        title={label}
        className="flex cursor-default items-center gap-2 rounded-lg border border-border bg-sidebar px-2.5 py-2 select-none"
      >
        <Building2 className="size-3.5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0">
          <div className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
            {t('shell.tenant.label')}
          </div>
          <div className="truncate text-sm font-semibold text-foreground">{label}</div>
        </div>
      </div>
    </div>
  );
}

function ProfileMenu({
  userLabel,
  onLogout,
}: {
  userLabel: string | null;
  onLogout: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        title={t('shell.profile.label')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'rounded-md p-0.5 text-muted-foreground outline-none transition-colors',
          'hover:text-foreground focus-visible:ring-2 focus-visible:ring-nav-active/40',
          open && 'text-foreground',
        )}
      >
        <User className="size-[18px]" strokeWidth={1.8} aria-hidden />
        <span className="sr-only">{t('shell.profile.label')}</span>
      </button>
      {open ? (
        <div
          role="menu"
          aria-label={t('shell.profile.label')}
          className="absolute bottom-[calc(100%+8px)] left-0 z-20 min-w-[180px] rounded-lg border border-border bg-card py-1.5 text-foreground shadow-md"
        >
          <div className="border-b border-border px-3 py-2">
            <div className="text-[11px] tracking-wide text-muted-foreground uppercase">
              {t('shell.profile.signedIn')}
            </div>
            <div className="truncate text-sm font-medium" title={userLabel ?? undefined}>
              <strong>{userLabel ?? t('shell.profile.unknownUser')}</strong>
            </div>
          </div>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <LogOut className="size-3.5 text-muted-foreground" aria-hidden />
            {t('shell.profile.logOut')}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function NavRow({
  item,
  active,
  linkLiveNav,
}: {
  item: NavItem;
  active: boolean;
  linkLiveNav: boolean;
}) {
  const { t } = useTranslation();
  const label = t(item.labelKey);
  const Icon = item.icon;
  const rowClass = cn(
    'relative -ml-[3px] flex items-center gap-2.5 rounded-lg border-l-[3px] px-3 py-2.5 no-underline',
    active ? 'border-nav-active bg-nav-active/10' : 'border-transparent',
  );
  const iconClass = cn('size-[18px]', active ? 'text-nav-active' : 'text-muted-foreground');
  const labelClass = cn('text-sm', active ? 'font-semibold text-foreground' : 'text-foreground');

  if (item.live && item.to && linkLiveNav) {
    return (
      <NavLink
        to={item.to}
        end={item.to === '/'}
        aria-current={active ? 'page' : undefined}
        className={rowClass}
      >
        <Icon className={iconClass} strokeWidth={active ? 2 : 1.8} aria-hidden />
        <span className={labelClass}>{label}</span>
      </NavLink>
    );
  }

  if (item.live) {
    return (
      <div aria-current={active ? 'page' : undefined} className={rowClass}>
        <Icon className={iconClass} strokeWidth={active ? 2 : 1.8} aria-hidden />
        <span className={labelClass}>{label}</span>
      </div>
    );
  }

  // Inert: full-opacity mockup look, not greyed-out disabled.
  return (
    <div
      aria-disabled="true"
      className="flex cursor-default items-center gap-2.5 rounded-lg px-3 py-2.5 select-none"
    >
      <Icon className="size-[18px] text-muted-foreground" strokeWidth={1.8} aria-hidden />
      <span className="text-sm text-foreground">{label}</span>
    </div>
  );
}

function CollapsibleGroup({
  label,
  icon: Icon,
  open,
  onToggle,
  children,
}: {
  label: string;
  icon: LucideIcon;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2.5">
          <Icon className="size-[18px] text-muted-foreground" strokeWidth={1.8} aria-hidden />
          <span className="text-sm text-foreground">{label}</span>
        </span>
        <ChevronDown
          className={cn(
            'size-3.5 text-muted-foreground transition-transform',
            open ? 'rotate-0' : '-rotate-90',
          )}
          aria-hidden
        />
      </button>
      {open ? <div className="flex flex-col gap-px pl-10">{children}</div> : null}
    </div>
  );
}

function InertChild({ label }: { label: string }) {
  return (
    <div
      aria-disabled="true"
      className="cursor-default rounded-md px-2 py-1.5 text-[13.5px] text-muted-foreground select-none"
    >
      {label}
    </div>
  );
}

/** A live nested nav link (Templates modeler map, ticket 02) — same size/spacing as InertChild, active state driven by NavLink itself. */
function LiveChild({ label, to }: { label: string; to: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'rounded-md px-2 py-1.5 text-[13.5px] no-underline',
          isActive ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground',
        )
      }
    >
      {label}
    </NavLink>
  );
}

function ExternalChild({ label, href }: { label: string; href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="rounded-md px-2 py-1.5 text-[13.5px] text-muted-foreground no-underline hover:text-foreground"
    >
      {label}
    </a>
  );
}

function FooterIcon({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span aria-disabled="true" title={label} className="cursor-default">
      <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}

function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const { t } = useTranslation();
  const isDark = theme === 'dark';
  const Icon = isDark ? Moon : Sun;
  const label = isDark ? t('shell.theme.switchToLight') : t('shell.theme.switchToDark');

  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onToggle}
      className="rounded-md p-0.5 text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-nav-active/40"
    >
      <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
    </button>
  );
}

function LocaleMenu() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  // First code in i18next's fallback chain that is one of our options, so a regional code (de-DE) still checks "de".
  const currentLocale =
    i18n.languages.find((lng) => LOCALE_OPTIONS.some((option) => option.value === lng)) ?? 'en-US';

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        title={t('shell.locale.label')}
        aria-label={t('shell.locale.label')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'rounded-md p-0.5 text-muted-foreground outline-none transition-colors',
          'hover:text-foreground focus-visible:ring-2 focus-visible:ring-nav-active/40',
          open && 'text-foreground',
        )}
      >
        <Flag className="size-[18px]" strokeWidth={1.8} aria-hidden />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label={t('shell.locale.menu')}
          className="absolute bottom-[calc(100%+8px)] left-1/2 z-20 min-w-[170px] -translate-x-1/2 rounded-lg border border-border bg-card py-1.5 text-foreground shadow-md"
        >
          <div className="px-3 py-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">
            {t('shell.locale.language')}
          </div>
          {LOCALE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="menuitemradio"
              lang={option.value}
              aria-checked={option.value === currentLocale}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
              onClick={() => {
                void i18n.changeLanguage(option.value);
                setOpen(false);
              }}
            >
              {option.label}
              {option.value === currentLocale ? <span aria-hidden>✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
