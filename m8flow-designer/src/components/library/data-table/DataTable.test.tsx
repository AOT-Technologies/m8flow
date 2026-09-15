import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DataTable, type DataTableColumn } from './DataTable';

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [
  { id: '1', name: 'Priya Shah' },
  { id: '2', name: 'Marcus Lee' },
];

const columns: DataTableColumn<Row>[] = [{ key: 'name', header: 'Name' }];

describe('DataTable', () => {
  it('renders plain, non-interactive rows when onRowClick is omitted', () => {
    render(<DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} />);

    const row = screen.getByText('Priya Shah').closest('[data-slot="data-table-row"]');
    expect(row).toHaveAttribute('role', 'row');
    expect(row).not.toHaveAttribute('tabindex');
  });

  it('fires onRowClick with the row and index when a row is clicked', () => {
    const onRowClick = vi.fn();
    render(
      <DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} onRowClick={onRowClick} />,
    );

    fireEvent.click(screen.getByText('Marcus Lee'));
    expect(onRowClick).toHaveBeenCalledWith(rows[1], 1);
  });

  it('marks clickable rows as role="button" with a tabbable, Enter/Space-activatable target', () => {
    const onRowClick = vi.fn();
    render(
      <DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} onRowClick={onRowClick} />,
    );

    const row = screen.getByRole('button', { name: 'Priya Shah' });
    expect(row).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(row, { key: 'Enter' });
    expect(onRowClick).toHaveBeenCalledWith(rows[0], 0);

    onRowClick.mockClear();
    fireEvent.keyDown(row, { key: ' ' });
    expect(onRowClick).toHaveBeenCalledWith(rows[0], 0);

    onRowClick.mockClear();
    fireEvent.keyDown(row, { key: 'Tab' });
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("lets a column's own render cell stop its click from also firing onRowClick", () => {
    const onRowClick = vi.fn();
    const onActionClick = vi.fn();
    const columnsWithAction: DataTableColumn<Row>[] = [
      { key: 'name', header: 'Name' },
      {
        key: 'actions',
        header: 'Actions',
        render: () => (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onActionClick();
            }}
          >
            Open
          </button>
        ),
      },
    ];

    render(
      <DataTable
        columns={columnsWithAction}
        rows={rows}
        getRowKey={(row) => row.id}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[0]);
    expect(onActionClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
