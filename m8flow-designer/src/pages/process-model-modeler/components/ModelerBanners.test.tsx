import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { NotPrimaryBanner } from './ModelerBanners';

describe('NotPrimaryBanner', () => {
  it('shows a file name containing markup as plain text', () => {
    const { container } = render(<NotPrimaryBanner primaryFileName="a <i>b</i> & c.bpmn" />);

    expect(screen.getByText('a <i>b</i> & c.bpmn')).toHaveClass('font-mono');
    expect(container.querySelector('i')).toBeNull();
  });
});
