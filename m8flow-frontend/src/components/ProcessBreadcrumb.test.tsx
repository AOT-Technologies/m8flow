import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProcessBreadcrumb from './ProcessBreadcrumb';

const h = vi.hoisted(() => ({
  can: ((_method: string, _uri: string) => false) as (
    method: string,
    uri: string,
  ) => boolean,
  permissionsLoaded: true,
}));

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: (method: string, uri: string) => h.can(method, uri) },
    permissionsLoaded: h.permissionsLoaded,
  })),
}));

vi.mock('@spiff-core/components/ProcessBreadcrumb', () => ({
  default: () => (
    <a href="/process-groups" data-testid="upstream-breadcrumb">
      crumb
    </a>
  ),
}));

describe('ProcessBreadcrumb', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.can = () => false;
    h.permissionsLoaded = true;
  });

  it('disables pointer events when GET /v1.0/process-groups is not granted', () => {
    h.can = () => false;
    render(<ProcessBreadcrumb hotCrumbs={[['Home', '/']]} />);
    const crumb = screen.getByTestId('upstream-breadcrumb');
    expect(crumb.parentElement).toHaveStyle({ pointerEvents: 'none' });
  });

  it('disables pointer events while permissions are still loading', () => {
    h.permissionsLoaded = false;
    h.can = () => true;
    render(<ProcessBreadcrumb hotCrumbs={[['Home', '/']]} />);
    const crumb = screen.getByTestId('upstream-breadcrumb');
    expect(crumb.parentElement).toHaveStyle({ pointerEvents: 'none' });
  });

  it('leaves navigation interactive when GET /v1.0/process-groups is granted', () => {
    h.can = (method, uri) =>
      method === 'GET' && uri === '/v1.0/process-groups';
    render(<ProcessBreadcrumb hotCrumbs={[['Home', '/']]} />);
    const crumb = screen.getByTestId('upstream-breadcrumb');
    expect(crumb.parentElement).not.toHaveStyle({ pointerEvents: 'none' });
  });
});
