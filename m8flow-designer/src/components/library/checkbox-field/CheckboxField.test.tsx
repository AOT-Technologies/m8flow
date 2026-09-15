import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CheckboxField } from './CheckboxField';

describe('CheckboxField', () => {
  it('renders unchecked and reports the flip to checked when the checkbox itself is clicked', () => {
    const onCheckedChange = vi.fn();
    render(<CheckboxField label="Notify on completion" checked={false} onCheckedChange={onCheckedChange} />);

    const checkbox = screen.getByRole('checkbox', { name: 'Notify on completion' });
    expect(checkbox).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(checkbox);

    expect(onCheckedChange).toHaveBeenCalledTimes(1);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('renders checked when checked=true and reports the flip to unchecked when the label text is clicked', () => {
    const onCheckedChange = vi.fn();
    render(<CheckboxField label="Notify on completion" checked onCheckedChange={onCheckedChange} />);

    const checkbox = screen.getByRole('checkbox', { name: 'Notify on completion' });
    expect(checkbox).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByText('Notify on completion'));

    expect(onCheckedChange).toHaveBeenCalledTimes(1);
    expect(onCheckedChange).toHaveBeenCalledWith(false);
  });

  it('does not report a change when disabled', () => {
    const onCheckedChange = vi.fn();
    render(
      <CheckboxField label="Notify on completion" checked={false} onCheckedChange={onCheckedChange} disabled />,
    );

    fireEvent.click(screen.getByText('Notify on completion'));

    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
