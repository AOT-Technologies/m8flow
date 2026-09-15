import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AddProcessModelFileDialog, fileOpensInModeler } from './AddProcessModelFileDialog';

describe('fileOpensInModeler', () => {
  it('opens BPMN, DMN, JSON, and Markdown in the modeler', () => {
    expect(fileOpensInModeler('a.bpmn')).toBe(true);
    expect(fileOpensInModeler('a.dmn')).toBe(true);
    expect(fileOpensInModeler('form.json')).toBe(true);
    expect(fileOpensInModeler('notes.md')).toBe(true);
    expect(fileOpensInModeler('notes.txt')).toBe(false);
  });
});

describe('AddProcessModelFileDialog', () => {
  it('submits a default BPMN name with the .bpmn suffix', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onCreated = vi.fn();
    render(
      <AddProcessModelFileDialog
        open
        onClose={vi.fn()}
        existingNames={[]}
        onCreate={onCreate}
        onCreated={onCreated}
      />,
    );
    fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'extra' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add file' }));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({ file_name: 'extra.bpmn' });
    });
    expect(onCreated).toHaveBeenCalledWith('extra.bpmn');
  });

  it('tells the user markdown opens in the modeler', () => {
    render(
      <AddProcessModelFileDialog
        open
        onClose={vi.fn()}
        existingNames={[]}
        onCreate={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    expect(screen.getByText(/JSON, and Markdown open in the modeler/)).toBeInTheDocument();
  });

  it('blocks a name that already exists', async () => {
    const onCreate = vi.fn();
    render(
      <AddProcessModelFileDialog
        open
        onClose={vi.fn()}
        existingNames={['notes.md']}
        onCreate={onCreate}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText('File type'), { target: { value: 'md' } });
    fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'notes.md' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add file' }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/already exists/i);
    });
    expect(onCreate).not.toHaveBeenCalled();
  });
});
