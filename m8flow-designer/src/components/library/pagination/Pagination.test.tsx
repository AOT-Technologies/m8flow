import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Pagination, buildPageWindow } from './Pagination';

describe('buildPageWindow', () => {
  it('shows every page when the total is small (<= 7)', () => {
    expect(buildPageWindow(1, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(buildPageWindow(4, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('collapses a large page count around the current page with one ellipsis on each side', () => {
    expect(buildPageWindow(12, 200)).toEqual([1, 'ellipsis', 11, 12, 13, 'ellipsis', 200]);
  });

  it('drops the leading ellipsis when the current page is near the start', () => {
    expect(buildPageWindow(2, 200)).toEqual([1, 2, 3, 'ellipsis', 200]);
  });

  it('drops the trailing ellipsis when the current page is near the end', () => {
    expect(buildPageWindow(199, 200)).toEqual([1, 'ellipsis', 198, 199, 200]);
  });

  it('never duplicates adjacent page numbers into a spurious ellipsis', () => {
    // current ± 1 touches the boundary pages directly — no gap, no ellipsis.
    expect(buildPageWindow(2, 8)).toEqual([1, 2, 3, 'ellipsis', 8]);
  });
});

describe('Pagination (counted mode)', () => {
  it('renders the range label and calls onPageChange for a page button', () => {
    const onPageChange = vi.fn();
    render(<Pagination page={1} onPageChange={onPageChange} totalItems={11} pageSize={5} />);

    expect(screen.getByText('1–5 of 11')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('disables Previous on the first page and Next on the last page', () => {
    const { rerender } = render(
      <Pagination page={1} onPageChange={vi.fn()} totalItems={11} pageSize={5} />,
    );
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).not.toBeDisabled();

    rerender(<Pagination page={3} onPageChange={vi.fn()} totalItems={11} pageSize={5} />);
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('renders a truncated page-button row with ellipses for a large page count', () => {
    render(<Pagination page={12} onPageChange={vi.fn()} totalItems={1000} pageSize={5} />);

    expect(screen.getByRole('button', { name: 'Page 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page 200' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page 11' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page 12' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page 13' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Page 50' })).not.toBeInTheDocument();
    // Two ellipsis gaps (before and after the current-page cluster).
    expect(screen.getAllByText('…')).toHaveLength(2);
  });

  it('does not render a rows-per-page selector unless both pageSizeOptions and onPageSizeChange are provided', () => {
    render(<Pagination page={1} onPageChange={vi.fn()} totalItems={11} pageSize={5} />);
    expect(screen.queryByText('Rows per page')).not.toBeInTheDocument();
  });

  it('renders a rows-per-page selector and reports a size change', () => {
    const onPageSizeChange = vi.fn();
    render(
      <Pagination
        page={1}
        onPageChange={vi.fn()}
        totalItems={42}
        pageSize={5}
        pageSizeOptions={[5, 10, 25]}
        onPageSizeChange={onPageSizeChange}
      />,
    );

    const select = screen.getByLabelText('Rows per page') as HTMLSelectElement;
    expect(select).toHaveValue('5');
    fireEvent.change(select, { target: { value: '25' } });
    expect(onPageSizeChange).toHaveBeenCalledWith(25);
  });
});

describe('Pagination (hasMore mode)', () => {
  it('renders a plain "Page N" label instead of a range, with no numbered buttons', () => {
    render(<Pagination page={2} onPageChange={vi.fn()} hasMore />);

    expect(screen.getByText('Page 2')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Page \d+$/ })).not.toBeInTheDocument();
  });

  it('disables Next when hasMore is false, and Previous at page 1', () => {
    const { rerender } = render(<Pagination page={1} onPageChange={vi.fn()} hasMore={false} />);
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();

    rerender(<Pagination page={2} onPageChange={vi.fn()} hasMore />);
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).not.toBeDisabled();
  });

  it('calls onPageChange with the next/previous page number', () => {
    const onPageChange = vi.fn();
    render(<Pagination page={2} onPageChange={onPageChange} hasMore />);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(3);
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});
