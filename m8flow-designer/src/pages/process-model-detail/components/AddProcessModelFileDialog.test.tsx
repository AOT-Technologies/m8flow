import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { chooseOption } from '@/test/chooseOption';

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
    await chooseOption(screen.getByRole('combobox', { name: 'File type' }), 'Markdown');
    fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'notes.md' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add file' }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/already exists/i);
    });
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('waits for the selected upload to finish reading before creating it', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <AddProcessModelFileDialog
        open
        onClose={vi.fn()}
        existingNames={[]}
        onCreate={onCreate}
        onCreated={vi.fn()}
      />,
    );
    await chooseOption(screen.getByRole('combobox', { name: 'File type' }), 'Upload');
    fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'invalid.bpmn' } });
    fireEvent.change(screen.getByLabelText('Upload file'), {
      target: { files: [new File(['<bpmn:definitions'], 'invalid.bpmn', { type: 'application/xml' })] },
    });

    const addButton = screen.getByRole('button', { name: 'Add file' });
    await waitFor(() => expect(addButton).toBeEnabled());
    fireEvent.click(addButton);
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({ file_name: 'invalid.bpmn', content: '<bpmn:definitions' });
    });
  });

  it('keeps rejected uploads open and displays the backend validation error', async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error('Unsupported BPMN construct'));
    render(
      <AddProcessModelFileDialog
        open
        onClose={vi.fn()}
        existingNames={[]}
        onCreate={onCreate}
        onCreated={vi.fn()}
      />,
    );
    await chooseOption(screen.getByRole('combobox', { name: 'File type' }), 'Upload');
    fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'invalid.bpmn' } });
    fireEvent.change(screen.getByLabelText('Upload file'), {
      target: { files: [new File(['<bpmn:definitions'], 'invalid.bpmn', { type: 'application/xml' })] },
    });
    const addButton = screen.getByRole('button', { name: 'Add file' });
    await waitFor(() => expect(addButton).toBeEnabled());

    fireEvent.click(addButton);

    expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported BPMN construct');
    expect(screen.getByRole('dialog', { name: 'Add file' })).toBeInTheDocument();
    expect(onCreate).toHaveBeenCalledWith({ file_name: 'invalid.bpmn', content: '<bpmn:definitions' });
  });
});
