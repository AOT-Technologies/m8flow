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
});
