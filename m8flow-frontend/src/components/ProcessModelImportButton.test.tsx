import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ProcessModelImportButton } from './ProcessModelImportButton';

describe('ProcessModelImportButton', () => {
  it('always renders nothing', () => {
    const { container } = render(
      <ProcessModelImportButton onClick={() => undefined} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
