import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Chip } from './Chip';

describe('Chip', () => {
  it('fires onClick when enabled', () => {
    const onClick = vi.fn();
    render(<Chip onClick={onClick}>Any status</Chip>);

    fireEvent.click(screen.getByRole('button', { name: /Any status/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when disabled, and marks itself aria-disabled', () => {
    const onClick = vi.fn();
    render(
      <Chip disabled onClick={onClick}>
        Any status
      </Chip>,
    );

    const chip = screen.getByRole('button', { name: /Any status/ });
    expect(chip).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(chip);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders the plain filter (chevron) shape when both disabled and removable are set, not the removable (X) shape', () => {
    const onRemove = vi.fn();
    render(
      <Chip disabled removable onRemove={onRemove}>
        Any status
      </Chip>,
    );

    expect(screen.getByRole('button', { name: /Any status/ })).toHaveAttribute(
      'data-variant',
      'filter',
    );
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  });

  it('still fires onRemove for a non-disabled removable chip', () => {
    const onRemove = vi.fn();
    render(
      <Chip removable onRemove={onRemove}>
        Marketing
      </Chip>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
