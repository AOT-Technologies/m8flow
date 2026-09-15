import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Sidebar } from './Sidebar';

describe('Sidebar live nav', () => {
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
