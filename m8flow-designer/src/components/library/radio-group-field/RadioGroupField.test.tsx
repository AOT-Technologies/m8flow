import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RadioGroupField } from './RadioGroupField';

const options = [
  { label: 'Manual', value: 'manual' },
  { label: 'Scheduled', value: 'scheduled' },
];

describe('RadioGroupField', () => {
  it('renders one labeled row per option, reflecting the selected option', () => {
    render(<RadioGroupField options={options} value="manual" onValueChange={vi.fn()} />);

    expect(screen.getByRole('radio', { name: 'Manual' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Scheduled' })).toHaveAttribute('aria-checked', 'false');
  });

  it('reports the newly selected option when its radio is clicked', () => {
    const onValueChange = vi.fn();
    render(<RadioGroupField options={options} value="manual" onValueChange={onValueChange} />);

    fireEvent.click(screen.getByRole('radio', { name: 'Scheduled' }));

    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(onValueChange).toHaveBeenCalledWith('scheduled');
  });

  it('reports the newly selected option when its label text is clicked', () => {
    const onValueChange = vi.fn();
    render(<RadioGroupField options={options} value="manual" onValueChange={onValueChange} />);

    fireEvent.click(screen.getByText('Scheduled'));

    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(onValueChange).toHaveBeenCalledWith('scheduled');
  });

  it('does not report a change when disabled', () => {
    const onValueChange = vi.fn();
    render(<RadioGroupField options={options} value="manual" onValueChange={onValueChange} disabled />);

    fireEvent.click(screen.getByText('Scheduled'));

    expect(onValueChange).not.toHaveBeenCalled();
  });
});
