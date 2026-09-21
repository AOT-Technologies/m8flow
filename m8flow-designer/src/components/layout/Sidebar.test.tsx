import { fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, MemoryRouter, Route, Routes, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { Sidebar } from './Sidebar';

afterEach(() => {
  window.localStorage.removeItem('m8flow_theme');
  window.localStorage.removeItem('m8flow_locale');
  document.documentElement.classList.remove('dark');
  document.documentElement.style.colorScheme = '';
  document.documentElement.lang = '';
});

describe('Sidebar live nav', () => {
  it('makes the Theme icon a working light/dark mode toggle', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    const themeToggle = screen.getByRole('button', { name: 'Switch to dark theme' });
    expect(document.documentElement).not.toHaveClass('dark');

    fireEvent.click(themeToggle);
    expect(document.documentElement).toHaveClass('dark');
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }));
    expect(document.documentElement).not.toHaveClass('dark');
  });

  it('makes the Locale icon open a selectable language menu', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    fireEvent.click(screen.getByRole('button', { name: 'Locale' }));
    const localeMenu = screen.getByRole('menu', { name: 'Locale options' });
    expect(localeMenu).toBeInTheDocument();
    expect(localeMenu).toHaveClass('left-1/2', '-translate-x-1/2');
    const english = screen.getByRole('menuitemradio', { name: /English \(US\)/ });
    expect(english).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(english);
    expect(screen.queryByRole('menu', { name: 'Locale options' })).not.toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute('lang', 'en-US');
  });

  it('renders Home and Processes as links inside a router', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Processes' })).toHaveAttribute(
      'href',
      '/processes',
    );
    // Process Instances + task-state map, ticket 02: now a real link too.
    expect(screen.getByRole('link', { name: 'Process Instances' })).toHaveAttribute(
      'href',
      '/process-instances',
    );
    // Templates is a live Setup child; Configuration is inert until secrets
    // read is granted (showConfiguration).
    expect(screen.getByRole('link', { name: 'Templates' })).toHaveAttribute(
      'href',
      '/templates',
    );
    expect(screen.getByText('Configuration')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Configuration' })).not.toBeInTheDocument();
    expect(screen.getByText('Connectors')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Connectors' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tenants' })).not.toBeInTheDocument();
    expect(screen.queryByText('Tenants')).not.toBeInTheDocument();
    expect(screen.queryByText('Tenant Management')).not.toBeInTheDocument();
  });

  it('shows a read-only active tenant badge and no tenant combobox', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar activeTenantLabel="Acme Corp" />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByTestId('nav-tenant-name')).toHaveTextContent('Acme Corp');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('renders the read-only chip (not a button) for a single-org membership', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <Sidebar
              activeTenantLabel="Acme Corp"
              organizations={[{ alias: 'acme', id: 'acme', name: 'Acme Corp' }]}
            />
          ),
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByTestId('nav-tenant-name')).toHaveTextContent('Acme Corp');
    expect(screen.queryByRole('button', { name: /Acme Corp/i })).not.toBeInTheDocument();
  });

  it('renders the interactive TenantSwitcher (ticket 06) for >=2 org memberships', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <Sidebar
              activeTenantLabel="Acme Corp"
              organizations={[
                { alias: 'acme', id: 'acme', name: 'Acme Corp' },
                { alias: 'globex', id: 'globex', name: 'Globex' },
              ]}
            />
          ),
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    const trigger = screen.getByTestId('nav-tenant-name');
    expect(trigger).toHaveTextContent('Acme Corp');
    expect(trigger.tagName).toBe('BUTTON');
  });

  it('prefers the super-admin tenant selector over the active-tenant badge', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <Sidebar
              showTenantSelector
              tenants={[{ id: 't1', name: 'Tenant One' }]}
              activeTenantLabel="Acme Corp"
            />
          ),
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('combobox', { name: /Tenant/ })).toBeInTheDocument();
    expect(screen.queryByTestId('nav-tenant-name')).not.toBeInTheDocument();
  });

  it('makes Configuration a live /configuration/secrets link when secrets can be read', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showConfiguration />,
        },
        {
          path: '/configuration/secrets',
          element: <Sidebar showConfiguration />,
        },
      ],
      { initialEntries: ['/configuration/secrets'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Configuration' })).toHaveAttribute(
      'href',
      '/configuration/secrets',
    );
  });

  it('omits Templates when the backend denies template read permission', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showTemplates={false} />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.queryByText('Templates')).not.toBeInTheDocument();
  });

  it('makes Connectors a live /connectors link when the catalog can be read', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showConnectors />,
        },
        {
          path: '/connectors',
          element: <Sidebar showConnectors />,
        },
      ],
      { initialEntries: ['/connectors'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Connectors' })).toHaveAttribute('href', '/connectors');
  });

  it('makes MCP Connection a live /mcp-connection link when it can be read', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Sidebar showMcpConnection />} />
          <Route path="/mcp-connection" element={<div>mcp-connection-destination</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const mcpLink = screen.getByRole('link', { name: 'MCP Connection' });
    expect(mcpLink).toHaveAttribute(
      'href',
      '/mcp-connection',
    );
    fireEvent.click(mcpLink);
    expect(screen.getByText('mcp-connection-destination')).toBeInTheDocument();
  });

  it('makes Messages a live /messages link when it can be read', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Sidebar showMessages />} />
          <Route path="/messages" element={<div>messages-destination</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const messagesLink = screen.getByRole('link', { name: 'Messages' });
    expect(messagesLink).toHaveAttribute('href', '/messages');
    fireEvent.click(messagesLink);
    expect(screen.getByText('messages-destination')).toBeInTheDocument();
  });

  it('makes Tenants a live /tenants link for super-admin', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showTenantsNav />,
        },
        {
          path: '/tenants',
          element: <Sidebar showTenantsNav />,
        },
      ],
      { initialEntries: ['/tenants'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Tenants' })).toHaveAttribute('href', '/tenants');
    expect(screen.getByRole('link', { name: 'Tenants' })).toHaveAttribute('aria-current', 'page');
  });

  it('makes configured System dashboards clickable external links', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <Sidebar
              showSystem
              celeryMonitoringUrl="http://localhost:6850/workers"
              natsMonitoringUrl="http://localhost:6852"
            />
          ),
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Celery' })).toHaveAttribute(
      'href',
      'http://localhost:6850/workers',
    );
    expect(screen.getByRole('link', { name: 'NATS' })).toHaveAttribute(
      'href',
      'http://localhost:6852',
    );
  });

  it('hides an unconfigured System dashboard', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showSystem celeryMonitoringUrl="http://localhost:6850/workers" />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Celery' })).toBeInTheDocument();
    expect(screen.queryByText('NATS')).not.toBeInTheDocument();
  });

  it('hides Tenants unless showTenantsNav is set', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showTenantManagement />,
        },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.queryByText('Tenants')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tenant Management' })).toBeInTheDocument();
  });

  it('keeps Tenants selected when a super-admin is on a tenant-management URL', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showTenantsNav />,
        },
        {
          path: '/tenants',
          element: <Sidebar showTenantsNav />,
        },
        {
          path: '/tenant-management/:tenantId',
          element: <Sidebar showTenantsNav />,
        },
      ],
      { initialEntries: ['/tenant-management/t1'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Tenants' })).toHaveClass('border-nav-active');
    expect(screen.queryByText('Tenant Management')).not.toBeInTheDocument();
  });

  it('shows Tenant Management as a live link when the role can manage the tenant', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <Sidebar showTenantManagement />,
        },
        {
          path: '/tenant-management',
          element: <Sidebar showTenantManagement />,
        },
      ],
      { initialEntries: ['/tenant-management'] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole('link', { name: 'Tenant Management' })).toHaveAttribute(
      'href',
      '/tenant-management',
    );
    expect(screen.getByRole('link', { name: 'Tenant Management' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('stays inert (no links) outside a router for prototypes', () => {
    render(<Sidebar activeNavId="home" />);

    expect(screen.queryByRole('link', { name: 'Home' })).not.toBeInTheDocument();
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Processes')).toBeInTheDocument();
  });
});
