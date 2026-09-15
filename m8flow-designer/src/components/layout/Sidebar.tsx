import {
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
  Server,
  Sun,
  User,
  Users,
} from 'lucide-react';
import { NavLink, useInRouterContext, useLocation } from 'react-router-dom';

import { cn } from '@/lib/utils';
import type { OrganizationMembership } from '@/lib/auth';
import { TenantSwitcher } from './TenantSwitcher';

export type SidebarTenant = {
  id: string;
  name: string;
};

export type LiveNavId = 'home' | 'tenants' | 'tenant-management' | 'processes' | 'process-instances' | 'task-review';

export type SidebarProps = {
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
  /** Super-admin: Tenants nav is a live `/tenants` link. Hidden otherwise. */
  showTenantsNav?: boolean;
  /** Tenant-admin: Tenant Management is a live `/tenant-management` link. Hidden for super-admin (they enter via Tenants). */
  showTenantManagement?: boolean;
  className?: string;
};

type LucideIcon = ComponentType<SVGProps<SVGSVGElement> & { className?: string }>;

type NavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Route path when this item is a live link. */
  to?: string;
  live?: boolean;
};

const TOP_NAV: NavItem[] = [
  { id: 'home', label: 'Home', icon: Home, to: '/', live: true },
  { id: 'tenants', label: 'Tenants', icon: Building2, to: '/tenants', live: true },
  {
    id: 'tenant-management',
    label: 'Tenant Management',
    icon: Users,
    to: '/tenant-management',
    live: true,
  },
  { id: 'processes', label: 'Processes', icon: GitBranch, to: '/processes', live: true },
  {
    id: 'process-instances',
    label: 'Process Instances',
    icon: Activity,
    to: '/process-instances',
    live: true,
  },
  { id: 'task-review', label: 'Task Review', icon: ClipboardCheck, to: '/task-review', live: true },
  { id: 'messages', label: 'Messages', icon: Mail },
  { id: 'mcp', label: 'MCP Connection', icon: Link2 },
];

type SidebarChild = {
  label: string;
  /** Route path when this child is a live link (Templates modeler map, ticket 02). */
  to?: string;
};

const SETUP_CHILDREN: SidebarChild[] = [
  { label: 'Configuration' },
  { label: 'Connectors' },
  { label: 'Templates', to: '/templates' },
];
const CONFIGURATION_CHILD: SidebarChild = {
  label: 'Configuration',
  to: '/configuration/secrets',
};
const CONNECTORS_CHILD: SidebarChild = {
  label: 'Connectors',
  to: '/connectors',
};
const SYSTEM_CHILDREN: SidebarChild[] = [{ label: 'Celery' }, { label: 'NATS' }];

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
  showTenantsNav = false,
  showTenantManagement = false,
  activeTenantLabel = null,
  organizations = [],
  className,
}: SidebarProps & { linkLiveNav?: boolean }) {
  const [setupOpen, setSetupOpen] = useState(true);
  const [systemOpen, setSystemOpen] = useState(true);
  const setupChildren = [
    showConfiguration ? CONFIGURATION_CHILD : SETUP_CHILDREN[0],
    showConnectors ? CONNECTORS_CHILD : SETUP_CHILDREN[1],
    SETUP_CHILDREN[2],
  ];

  const topNav = TOP_NAV.filter((item) => {
    if (item.id === 'tenants') {
      return showTenantsNav;
    }
    if (item.id === 'tenant-management') {
      return showTenantManagement;
    }
    return true;
  });

  const selectedLabel =
    selectedTenantId == null
      ? 'All Tenants'
      : (tenants.find((t) => t.id === selectedTenantId)?.name ?? selectedTenantId);

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
            Tenant
          </div>
          <label className="relative block">
            <span className="sr-only">Tenant</span>
            <select
              className="w-full appearance-none rounded-lg border border-border bg-sidebar py-2 pr-8 pl-2.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-nav-active/40"
              value={selectedTenantId ?? ''}
              onChange={(event) => {
                const value = event.target.value;
                onTenantChange?.(value === '' ? null : value);
              }}
            >
              <option value="">All Tenants</option>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
            <ChevronDown
              className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            {/* Visible label mirror for the closed native select's look — the
                select itself drives value; this keeps the mockup's "All Tenants
                + chevron" reading when options are sparse. */}
            <span className="sr-only">{selectedLabel}</span>
          </label>
        </div>
      ) : activeTenantLabel && organizations.length >= 2 ? (
        <TenantSwitcher activeTenantLabel={activeTenantLabel} organizations={organizations} />
      ) : activeTenantLabel ? (
        <div className="px-6 pb-4">
          <div
            data-testid="nav-tenant-name"
            title={activeTenantLabel}
            className="flex cursor-default items-center gap-2 rounded-lg border border-border bg-sidebar px-2.5 py-2 select-none"
          >
            <Building2 className="size-3.5 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0">
              <div className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
                Tenant
              </div>
              <div className="truncate text-sm font-semibold text-foreground">
                {activeTenantLabel}
              </div>
            </div>
          </div>
        </div>
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

        <CollapsibleGroup
          label="Setup"
          icon={ListFilter}
          open={setupOpen}
          onToggle={() => setSetupOpen((open) => !open)}
        >
          {setupChildren.map((child) =>
            child.to && linkLiveNav ? (
              <LiveChild key={child.label} label={child.label} to={child.to} />
            ) : (
              <InertChild key={child.label} label={child.label} />
            ),
          )}
        </CollapsibleGroup>

        <CollapsibleGroup
          label="System"
          icon={Server}
          open={systemOpen}
          onToggle={() => setSystemOpen((open) => !open)}
        >
          {SYSTEM_CHILDREN.map((child) => (
            <InertChild key={child.label} label={child.label} />
          ))}
        </CollapsibleGroup>
      </nav>

      <div className="flex items-center gap-4 border-t border-border px-6 py-4 text-muted-foreground">
        {onLogout ? (
          <ProfileMenu userLabel={userLabel} onLogout={onLogout} />
        ) : (
          <FooterIcon icon={User} label="Profile" />
        )}
        <FooterIcon icon={Sun} label="Theme" />
        <FooterIcon icon={Flag} label="Locale" />
      </div>
    </aside>
  );
}

function ProfileMenu({
  userLabel,
  onLogout,
}: {
  userLabel: string | null;
  onLogout: () => void;
}) {
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
        title="Profile"
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
        <span className="sr-only">Profile</span>
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Profile"
          className="absolute bottom-[calc(100%+8px)] left-0 z-20 min-w-[180px] rounded-lg border border-border bg-card py-1.5 text-foreground shadow-md"
        >
          <div className="border-b border-border px-3 py-2">
            <div className="text-[11px] tracking-wide text-muted-foreground uppercase">
              Signed in
            </div>
            <div className="truncate text-sm font-medium" title={userLabel ?? undefined}>
              <strong>{userLabel ?? 'unknown user'}</strong>
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
            Log out
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
        <span className={labelClass}>{item.label}</span>
      </NavLink>
    );
  }

  if (item.live) {
    return (
      <div aria-current={active ? 'page' : undefined} className={rowClass}>
        <Icon className={iconClass} strokeWidth={active ? 2 : 1.8} aria-hidden />
        <span className={labelClass}>{item.label}</span>
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
      <span className="text-sm text-foreground">{item.label}</span>
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

function FooterIcon({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span aria-disabled="true" title={label} className="cursor-default">
      <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}
