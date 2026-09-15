import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BackLink, Breadcrumbs } from './Breadcrumbs';

const items = [
  { label: 'Processes', href: '/processes' },
  { label: 'Invoice Approvals / Finance', href: '/processes/invoice-approvals' },
  { label: 'Two-step invoice approval' },
];

describe('Breadcrumbs', () => {
  it('renders linked crumbs as plain anchors by default', () => {
    render(<Breadcrumbs items={items} />);

    const link = screen.getByRole('link', { name: 'Processes' });
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/processes');
  });

  it('defaults linked crumbs to text-primary, overridable via linkClassName', () => {
    const { rerender } = render(<Breadcrumbs items={items} />);
    expect(screen.getByRole('link', { name: 'Processes' })).toHaveClass('text-primary');

    rerender(<Breadcrumbs items={items} linkClassName="text-info" />);
    const link = screen.getByRole('link', { name: 'Processes' });
    expect(link).toHaveClass('text-info');
    expect(link).not.toHaveClass('text-primary');
  });

  it('defaults the last crumb to plain prose styling, overridable via lastClassName', () => {
    const { rerender } = render(<Breadcrumbs items={items} />);
    const lastCrumb = screen.getByText('Two-step invoice approval');
    expect(lastCrumb).not.toHaveClass('font-mono');

    rerender(<Breadcrumbs items={items} lastClassName="font-mono" />);
    expect(screen.getByText('Two-step invoice approval')).toHaveClass('font-mono');
  });

  it('renders every non-last linked crumb through a custom LinkComponent when provided', () => {
    function FakeRouterLink({
      href,
      className,
      children,
    }: {
      href: string;
      className?: string;
      children: React.ReactNode;
    }) {
      return (
        <a href={href} className={className} data-fake-router-link="true">
          {children}
        </a>
      );
    }

    render(<Breadcrumbs items={items} LinkComponent={FakeRouterLink} />);

    const processesLink = screen.getByRole('link', { name: 'Processes' });
    const groupLink = screen.getByRole('link', { name: 'Invoice Approvals / Finance' });
    expect(processesLink).toHaveAttribute('data-fake-router-link', 'true');
    expect(groupLink).toHaveAttribute('data-fake-router-link', 'true');
  });

  it('never renders the last crumb as a link, even with a custom LinkComponent and an href', () => {
    function FakeRouterLink({
      href,
      children,
    }: {
      href: string;
      className?: string;
      children: React.ReactNode;
    }) {
      return <a href={href}>{children}</a>;
    }

    render(
      <Breadcrumbs
        items={[...items.slice(0, -1), { label: 'Last crumb', href: '/last' }]}
        LinkComponent={FakeRouterLink}
      />,
    );

    expect(screen.queryByRole('link', { name: 'Last crumb' })).not.toBeInTheDocument();
    expect(screen.getByText('Last crumb')).toHaveAttribute('aria-current', 'page');
  });

  it('still renders an unlinked non-last crumb as plain text, not through LinkComponent', () => {
    function FakeRouterLink({
      href,
      children,
    }: {
      href: string;
      className?: string;
      children: React.ReactNode;
    }) {
      return <a href={href}>{children}</a>;
    }

    render(
      <Breadcrumbs
        items={[{ label: 'No href here' }, { label: 'Last crumb' }]}
        LinkComponent={FakeRouterLink}
      />,
    );

    expect(screen.queryByRole('link', { name: 'No href here' })).not.toBeInTheDocument();
    expect(screen.getByText('No href here')).toBeInTheDocument();
  });
});

describe('BackLink', () => {
  it('renders as a plain anchor by default', () => {
    render(<BackLink href="/processes">All processes</BackLink>);

    const link = screen.getByRole('link', { name: 'All processes' });
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/processes');
  });

  it('renders through a custom LinkComponent when both it and href are provided', () => {
    function FakeRouterLink({
      href,
      className,
      children,
    }: {
      href: string;
      className?: string;
      children: React.ReactNode;
    }) {
      return (
        <a href={href} className={className} data-fake-router-link="true">
          {children}
        </a>
      );
    }

    render(
      <BackLink href="/processes" LinkComponent={FakeRouterLink}>
        All processes
      </BackLink>,
    );

    expect(screen.getByRole('link', { name: 'All processes' })).toHaveAttribute(
      'data-fake-router-link',
      'true',
    );
  });

  it('falls back to a plain anchor when LinkComponent is provided without href', () => {
    function FakeRouterLink({
      href,
      children,
    }: {
      href: string;
      className?: string;
      children: React.ReactNode;
    }) {
      return <a href={href}>{children}</a>;
    }

    render(<BackLink LinkComponent={FakeRouterLink}>All processes</BackLink>);

    // Falls back to BackLink's own plain <a> (marked data-slot="back-link")
    // rather than FakeRouterLink, since FakeRouterLink has nothing to link
    // to without an href.
    const link = screen.getByText('All processes').closest('a');
    expect(link).toHaveAttribute('data-slot', 'back-link');
  });
});
