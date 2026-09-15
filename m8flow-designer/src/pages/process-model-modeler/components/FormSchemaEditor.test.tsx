import { createRef } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import { FormSchemaEditor, type FormSchemaEditorSession } from './FormSchemaEditor';
import { EMPTY_JSON } from './formSchemaFiles';

function makeSession(overrides: Partial<FormSchemaEditorSession> = {}): FormSchemaEditorSession {
  return {
    fileName: 'sample-form-schema.json',
    onReadFile: vi.fn().mockResolvedValue(EMPTY_JSON),
    onWriteFile: vi.fn().mockResolvedValue(undefined),
    onCreateFile: vi.fn().mockResolvedValue(undefined),
    onCommitted: vi.fn(),
    ...overrides,
  };
}

describe('FormSchemaEditor', () => {
  it('auto-creates companion files when the schema is missing', async () => {
    const session = makeSession({
      fileName: 'task-schema.json',
      createIfMissing: true,
      onReadFile: vi.fn().mockRejectedValue(Object.assign(new Error('missing'), { status: 404 })),
    });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(session.onCreateFile).toHaveBeenCalledTimes(3);
    });
    expect(session.onCreateFile).toHaveBeenNthCalledWith(1, 'task-schema.json', EMPTY_JSON);
    expect(session.onCreateFile).toHaveBeenNthCalledWith(2, 'task-uischema.json', EMPTY_JSON);
    expect(session.onCreateFile).toHaveBeenNthCalledWith(3, 'task-exampledata.json', EMPTY_JSON);
    expect(session.onCommitted).toHaveBeenCalledWith('task-schema.json');
    expect(screen.getByLabelText('JSON Schema editor')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create Files' })).not.toBeInTheDocument();
  });

  it('loads an existing schema file into the editor and preview', async () => {
    const schema = JSON.stringify({
      title: 'Sample Form',
      type: 'object',
      properties: { name: { type: 'string', title: 'Name' } },
    });
    const session = makeSession({
      fileName: 'sample-form-schema.json',
      onReadFile: vi.fn(async (name: string) => {
        if (name.endsWith('-schema.json')) return schema;
        return EMPTY_JSON;
      }),
    });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    expect(await screen.findByLabelText('JSON Schema editor')).toHaveValue(schema);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(session.onCommitted).not.toHaveBeenCalled();
    expect(session.onCreateFile).not.toHaveBeenCalled();
  });

  it('binds an existing auto-named schema onto the task', async () => {
    const session = makeSession({
      fileName: 'task-schema.json',
      createIfMissing: true,
    });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(session.onCommitted).toHaveBeenCalledWith('task-schema.json');
    });
    expect(session.onCreateFile).not.toHaveBeenCalled();
  });

  it('formats the active JSON tab and reports invalid JSON', async () => {
    const session = makeSession({
      onReadFile: vi.fn(async (name: string) => {
        if (name.endsWith('-schema.json')) return '{"title":"Compact"}';
        return EMPTY_JSON;
      }),
    });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    const editor = await screen.findByLabelText('JSON Schema editor');
    expect(screen.getByText('No problems')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Format' }));
    expect(editor).toHaveValue('{\n  "title": "Compact"\n}\n');

    fireEvent.change(editor, { target: { value: '{ not json' } });
    expect(screen.getByText('1 error, 0 warnings')).toBeInTheDocument();
    expect(screen.getByText(/Please check the JSON Schema for errors/)).toBeInTheDocument();
    expect(screen.getByText(/Line 1:/)).toBeInTheDocument();
  });

  it('switches UI Settings and Data View onto their own JSON and descriptions', async () => {
    const session = makeSession({
      fileName: 'task-schema.json',
      onReadFile: vi.fn(async (name: string) => {
        if (name.endsWith('-uischema.json')) return '{"name":{"ui:placeholder":"Type here"}}';
        if (name.endsWith('-exampledata.json')) return '{"name":"Ada"}';
        return '{"type":"object","properties":{"name":{"type":"string","title":"Name"}}}';
      }),
    });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    expect(await screen.findByLabelText('JSON Schema editor')).toBeInTheDocument();
    expect(
      screen.getByText(/The JSON Schema describes the structure of the data you want to collect/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'UI Settings' }));
    expect(screen.getByLabelText('UI Settings editor')).toHaveValue(
      '{"name":{"ui:placeholder":"Type here"}}',
    );
    expect(
      screen.getByText(/These UI Settings augment the JSON Schema, specifying how the web form should be displayed/),
    ).toBeInTheDocument();
    expect(screen.getByText('task-uischema.json')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Data View' }));
    expect(screen.getByLabelText('Data View editor')).toHaveValue('{"name":"Ada"}');
    expect(
      screen.getByText(/Data entered in the form to the right will appear below/),
    ).toBeInTheDocument();
    expect(screen.getByText('task-exampledata.json')).toBeInTheDocument();
  });

  it('inserts an example into the schema from the Examples tab', async () => {
    const session = makeSession({ fileName: 'task-schema.json' });
    render(<FormSchemaEditor session={session} onClose={vi.fn()} />);

    expect(await screen.findByLabelText('JSON Schema editor')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Examples' }));
    expect(
      screen.getByText(/try adding these example fields to your form/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Load' })[0]);

    const editor = (await screen.findByLabelText('JSON Schema editor')) as HTMLTextAreaElement;
    expect(JSON.parse(editor.value).properties.givenName.title).toBe('Given name');
    expect(screen.getByText('Given name')).toBeInTheDocument();
  });

  it('keeps tabs available after the schema JSON is cleared', async () => {
    render(<FormSchemaEditor session={makeSession()} onClose={vi.fn()} />);

    const editor = await screen.findByLabelText('JSON Schema editor');
    fireEvent.change(editor, { target: { value: '' } });

    expect(screen.getByRole('tab', { name: 'UI Settings' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'UI Settings' }));
    expect(screen.getByLabelText('UI Settings editor')).toBeInTheDocument();
  });

  it('closes without saving on Close', async () => {
    const session = makeSession();
    const onClose = vi.fn();
    render(<FormSchemaEditor session={session} onClose={onClose} />);

    expect(await screen.findByLabelText('JSON Schema editor')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('embeds as a page canvas without the modal chrome', async () => {
    render(<FormSchemaEditor variant="page" session={makeSession()} />);

    expect(await screen.findByLabelText('JSON Schema editor')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Edit JSON Schema' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Edit JSON Schema' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });

  it('opens the matching tab when the route file is a companion', async () => {
    render(
      <FormSchemaEditor
        variant="page"
        session={makeSession({ fileName: 'sample-form-uischema.json' })}
      />,
    );

    await screen.findByLabelText('UI Settings editor');
    expect(screen.getByRole('tab', { name: 'UI Settings' })).toHaveAttribute('aria-selected', 'true');
  });

  it('page saveXML writes all three companions and returns the open file', async () => {
    const session = makeSession({
      fileName: 'sample-form-schema.json',
      onReadFile: vi.fn(async (name: string) => {
        if (name.endsWith('-schema.json')) return '{"title":"A"}';
        return EMPTY_JSON;
      }),
    });
    const onDirtyChange = vi.fn();
    const ref = createRef<DiagramCanvasHandle>();
    render(
      <FormSchemaEditor
        ref={ref}
        variant="page"
        session={session}
        onDirtyChange={onDirtyChange}
      />,
    );

    const editor = await screen.findByLabelText('JSON Schema editor');
    fireEvent.change(editor, { target: { value: '{"title":"B"}' } });
    expect(onDirtyChange).toHaveBeenCalledWith(true);
    expect(session.onWriteFile).not.toHaveBeenCalled();

    await expect(ref.current?.saveXML()).resolves.toEqual({
      xml: '{"title":"B"}',
      baseline: {
        schema: '{"title":"B"}',
        ui: EMPTY_JSON,
        example: EMPTY_JSON,
      },
    });
    expect(session.onWriteFile).toHaveBeenCalledWith('sample-form-schema.json', '{"title":"B"}');
    expect(session.onWriteFile).toHaveBeenCalledWith('sample-form-uischema.json', EMPTY_JSON);
    expect(session.onWriteFile).toHaveBeenCalledWith('sample-form-exampledata.json', EMPTY_JSON);

    expect(
      ref.current?.markSaved({
        schema: '{"title":"B"}',
        ui: EMPTY_JSON,
        example: EMPTY_JSON,
      }),
    ).toBe(false);
    expect(onDirtyChange).toHaveBeenCalledWith(false);
  });

  it('flushes pending modal writes when Close is clicked during debounce', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const session = makeSession({ fileName: 'task-schema.json' });
    const onClose = vi.fn();
    render(<FormSchemaEditor session={session} onClose={onClose} />);

    const editor = await screen.findByLabelText('JSON Schema editor');
    session.onWriteFile.mockClear();
    fireEvent.change(editor, { target: { value: '{"title":"Pending"}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(session.onWriteFile).toHaveBeenCalledWith('task-schema.json', '{"title":"Pending"}');
    vi.useRealTimers();
  });
});
