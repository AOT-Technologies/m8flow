import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ActionMenu } from './ActionMenu';

// Radix's DropdownMenu doesn't open under plain fireEvent.click in jsdom —
// use @testing-library/user-event throughout, per the map's Notes.

describe('ActionMenu', () => {
  it('is closed until the trigger is clicked, then shows its items', async () => {
    const user = userEvent.setup();
    render(<ActionMenu triggerLabel="Instance actions" items={[{ label: 'Open', onSelect: vi.fn() }]} />);

    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Instance actions' }));
    expect(await screen.findByRole('menuitem', { name: 'Open' })).toBeInTheDocument();
  });

  it('calls the item onSelect and closes the menu when a row is clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ActionMenu items={[{ label: 'Copy link', onSelect }]} />);

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Copy link' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
  });

  it('closes on Escape without firing any onSelect', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ActionMenu items={[{ label: 'Open', onSelect }]} />);

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    expect(await screen.findByRole('menuitem', { name: 'Open' })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('renders a disabled item inert — no onSelect fires when clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ActionMenu items={[{ label: 'Save as template', disabled: true, onSelect }]} />);

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    const item = await screen.findByRole('menuitem', { name: 'Save as template' });
    expect(item).toHaveAttribute('aria-disabled', 'true');

    await user.click(item);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('supports keyboard navigation — ArrowDown then Enter selects the next item', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const onDelete = vi.fn();
    render(
      <ActionMenu
        items={[
          { label: 'Open', onSelect: onOpen },
          { label: 'Delete', destructive: true, onSelect: onDelete },
        ]}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await screen.findByRole('menuitem', { name: 'Open' });

    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
  });
});
