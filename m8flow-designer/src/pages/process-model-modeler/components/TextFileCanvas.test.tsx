import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import { TextFileCanvas } from './TextFileCanvas';

describe('TextFileCanvas', () => {
  it('renders JSON content and reports dirty on edit', () => {
    const onDirtyChange = vi.fn();
    render(
      <TextFileCanvas fileName="form.json" xml='{"title":"A"}' onDirtyChange={onDirtyChange} />,
    );

    expect(screen.getByLabelText('File editor')).toHaveValue('{"title":"A"}');
    fireEvent.change(screen.getByLabelText('File editor'), {
      target: { value: '{"title":"B"}' },
    });
    expect(onDirtyChange).toHaveBeenCalledWith(true);
  });

  it('saveXML returns the current text and markSaved clears dirty', async () => {
    const onDirtyChange = vi.fn();
    const ref = createRef<DiagramCanvasHandle>();
    render(
      <TextFileCanvas
        ref={ref}
        fileName="notes.md"
        xml="# Heading\n"
        onDirtyChange={onDirtyChange}
      />,
    );

    fireEvent.change(screen.getByLabelText('File editor'), {
      target: { value: '# Updated\n' },
    });
    await expect(ref.current?.saveXML()).resolves.toEqual({
      xml: '# Updated\n',
      baseline: '# Updated\n',
    });

    expect(ref.current?.markSaved('# Updated\n')).toBe(false);
    expect(onDirtyChange).toHaveBeenCalledWith(false);
  });

  it('formats JSON without sending it through a BPMN import', () => {
    render(<TextFileCanvas fileName="form.json" xml='{"title":"Compact"}' />);

    fireEvent.click(screen.getByRole('button', { name: 'Format' }));

    expect(screen.getByLabelText('File editor')).toHaveValue('{\n  "title": "Compact"\n}\n');
  });

  it('reports invalid JSON in the problems list', () => {
    render(<TextFileCanvas fileName="form.json" xml="{not json" />);

    expect(screen.getByText(/1 error/)).toBeInTheDocument();
    expect(screen.getByText(/Line 1:/)).toBeInTheDocument();
  });
});
