import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ToggleSwitch } from './ToggleSwitch';

describe('ToggleSwitch', () => {
  it('renders unchecked and reports the flip to checked when the switch itself is clicked', () => {
    const onCheckedChange = vi.fn();
    render(<ToggleSwitch label="Auto-retry on failure" checked={false} onCheckedChange={onCheckedChange} />);

    const toggle = screen.getByRole('switch', { name: 'Auto-retry on failure' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(toggle);

    expect(onCheckedChange).toHaveBeenCalledTimes(1);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('renders checked when checked=true and reports the flip to unchecked when the label text is clicked', () => {
    const onCheckedChange = vi.fn();
    render(<ToggleSwitch label="Auto-retry on failure" checked onCheckedChange={onCheckedChange} />);

    const toggle = screen.getByRole('switch', { name: 'Auto-retry on failure' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByText('Auto-retry on failure'));

    expect(onCheckedChange).toHaveBeenCalledTimes(1);
    expect(onCheckedChange).toHaveBeenCalledWith(false);
  });

  it('does not report a change when disabled', () => {
    const onCheckedChange = vi.fn();
    render(
      <ToggleSwitch label="Auto-retry on failure" checked={false} onCheckedChange={onCheckedChange} disabled />,
    );

    fireEvent.click(screen.getByText('Auto-retry on failure'));

    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
