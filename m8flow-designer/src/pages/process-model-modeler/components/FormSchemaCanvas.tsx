/**
 * Process-modeler page host for form-schema companion JSON. Same
 * FormSchemaEditor as User Task Launch Editor, without the modal overlay.
 * Implements DiagramCanvasHandle so page Save / Download / dirty / Cmd+S
 * flush all three companions and return the open file's text.
 */
import { forwardRef, useMemo } from 'react';

import { FormSchemaEditor, type FormSchemaEditorSession } from './FormSchemaEditor';
import type { DiagramCanvasHandle } from './DiagramCanvasHandle';

export type FormSchemaCanvasProps = {
  fileName: string;
  onDirtyChange?: (dirty: boolean) => void;
  onReadFile: (fileName: string) => Promise<string>;
  onWriteFile: (fileName: string, content: string) => Promise<void>;
  onCreateFile: (fileName: string, content: string) => Promise<void>;
};

export const FormSchemaCanvas = forwardRef<DiagramCanvasHandle, FormSchemaCanvasProps>(
  function FormSchemaCanvas(
    { fileName, onDirtyChange, onReadFile, onWriteFile, onCreateFile },
    ref,
  ) {
    const session = useMemo<FormSchemaEditorSession>(
      () => ({
        fileName,
        onReadFile,
        onWriteFile,
        onCreateFile,
        onCommitted: () => {},
      }),
      [fileName, onReadFile, onWriteFile, onCreateFile],
    );

    return (
      <FormSchemaEditor
        ref={ref}
        variant="page"
        session={session}
        onDirtyChange={onDirtyChange}
      />
    );
  },
);
