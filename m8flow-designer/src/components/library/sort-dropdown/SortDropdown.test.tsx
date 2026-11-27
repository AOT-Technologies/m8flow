import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SortDropdown } from './SortDropdown';

const OPTIONS = [
  { label: 'All', value: 'all', count: 5 },
  { label: 'Published', value: 'published', count: 5, description: 'Live models' },
  { label: 'Draft', value: 'draft', count: 0 },
];

describe('SortDropdown', () => {
  it.each([
    { key: 'ArrowDown', name: 'Draft 0', value: 'draft' },
    { key: 'ArrowUp', name: 'Draft review', value: 'draft-review' },
  ])('selects the filtered boundary result with $key when the current selection is hidden', async ({ key, name, value }) => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SortDropdown
        label="Status"
        options={[
          ...OPTIONS,
          { label: 'Draft review', value: 'draft-review' },
          { label: 'Archived', value: 'archived' },
        ]}
        value="published"
        onChange={onChange}
        searchPlaceholder="Search statuses"
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Status: Published' });
    await user.click(trigger);
    const search = await screen.findByRole('searchbox', { name: 'Search statuses' });
    await user.type(search, 'draft');
    expect(search).toHaveFocus();
    expect(screen.queryByRole('menuitemradio', { name: /^Published/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('menuitemradio')).toHaveLength(2);
    const result = screen.getByRole('menuitemradio', { name });
    expect(result).toHaveAttribute('aria-checked', 'false');
    await user.keyboard(`{${key}}`);
    expect(result).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onChange).toHaveBeenCalledExactlyOnceWith(value);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it.each(['ArrowDown', 'ArrowUp'])('keeps search focus with %s when no results match', async (key) => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SortDropdown
        label="Status"
        options={OPTIONS}
        value="published"
        onChange={onChange}
        searchPlaceholder="Search statuses"
        emptyLabel="No matching statuses"
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Status: Published' });
    await user.click(trigger);
    const search = await screen.findByRole('searchbox', { name: 'Search statuses' });
    await user.type(search, 'zzz');
    expect(screen.queryByRole('menuitemradio')).not.toBeInTheDocument();
    await user.keyboard(`{${key}}`);
    expect(search).toHaveFocus();
    expect(search).toHaveValue('zzz');
    expect(screen.getByText('No matching statuses')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('keeps counts out of the trigger and marks only the selected row checked', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SortDropdown label="Status" options={OPTIONS} value="published" onChange={onChange} />);

    const trigger = screen.getByRole('button', { name: 'Status: Published' });
    await user.click(trigger);

    const selected = await screen.findByRole('menuitemradio', { name: /^Published/ });
    expect(selected).toHaveAttribute('aria-checked', 'true');
    expect(selected).toHaveTextContent('Live models');
    expect(screen.getByRole('menuitemradio', { name: 'Draft 0' })).toHaveAttribute('aria-checked', 'false');

    // Keyboard: Escape closes; Enter reopens on the first row; arrows + Enter pick.
    await user.keyboard('{Escape}');
    trigger.focus();
    await user.keyboard('{Enter}');
    await screen.findByRole('menu');
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');
    expect(onChange).toHaveBeenCalledWith('draft');
  });

  it('filters rows by the search box when searchable', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SortDropdown
        label="Group"
        options={[
          { label: 'All groups', value: '' },
          { label: 'Finance', value: 'finance' },
          { label: 'HR', value: 'hr' },
        ]}
        value=""
        onChange={onChange}
        searchPlaceholder="Search groups"
        emptyLabel="No matching groups"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Group: All groups' }));
    const search = await screen.findByRole('searchbox', { name: 'Search groups' });
    expect(search).toHaveFocus();
    await user.type(search, 'fin');
    expect(screen.queryByRole('menuitemradio', { name: 'HR' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitemradio', { name: 'Finance' }));
    expect(onChange).toHaveBeenCalledWith('finance');

    await user.click(screen.getByRole('button', { name: 'Group: All groups' }));
    await user.type(await screen.findByRole('searchbox'), 'zzz');
    expect(screen.getByText('No matching groups')).toBeInTheDocument();
  });
});
