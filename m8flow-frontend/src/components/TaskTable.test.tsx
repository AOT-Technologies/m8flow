import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import TaskTable from './TaskTable';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('./TenantTaskTable', () => ({
  default: () => <div data-testid="tenant-task-table" />,
}));

vi.mock('@spiff-core/components/TaskTable', () => ({
  default: () => <div data-testid="upstream-task-table" />,
}));

import UserService from '../services/UserService';

describe('TaskTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders TenantTaskTable for super-admin table mode', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    render(<TaskTable entries={[]} viewMode="table" />);
    expect(screen.getByTestId('tenant-task-table')).toBeInTheDocument();
    expect(screen.queryByTestId('upstream-task-table')).toBeNull();
  });

  it('defaults to table mode for super-admin when viewMode is omitted', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    render(<TaskTable entries={[]} />);
    expect(screen.getByTestId('tenant-task-table')).toBeInTheDocument();
  });

  it('renders upstream TaskTable for super-admin non-table mode', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    render(<TaskTable entries={[]} viewMode="tile" />);
    expect(screen.getByTestId('upstream-task-table')).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-task-table')).toBeNull();
  });

  it('renders upstream TaskTable for non-super-admin table mode', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    render(<TaskTable entries={[]} viewMode="table" />);
    expect(screen.getByTestId('upstream-task-table')).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-task-table')).toBeNull();
  });
});
