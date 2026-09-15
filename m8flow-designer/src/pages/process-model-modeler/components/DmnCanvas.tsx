/**
 * Thin React host shell around `m8flow-bpmn/lib/DmnModeler`.
 * Stock dmn-js chrome, panel wiring, and DRD zoom (in / out / fit — the same
 * `zoomControlsModule` as BPMN) live in the package. This file owns
 * containers, dirty tracking across DMN views, and saveXML/markSaved.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import DmnModeler from 'm8flow-bpmn/lib/DmnModeler';

import type { DiagramCanvasHandle } from './DiagramCanvasHandle';

export type DmnCanvasProps = {
  xml: string;
  onDirtyChange?: (dirty: boolean) => void;
};

export const DmnCanvas = forwardRef<DiagramCanvasHandle, DmnCanvasProps>(function DmnCanvas(
  { xml, onDirtyChange },
  ref,
) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [modeler, setModeler] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  // dmn-js manages a separate diagram-js instance (and command stack) per
  // view (DRD / decision table / literal expression per decision) — unlike
  // BpmnCanvas's single command stack. This tracks only the *currently
  // active* view's stack index, re-baselining on each view switch. Known
  // limitation, not silently hidden: edits made in a view, then abandoned
  // by switching away without saving, won't keep reporting dirty once
  // re-baselined. saveXML() itself still exports the whole document
  // correctly regardless — only the dirty *indicator* has this gap.
  const savedStackIndexRef = useRef(-1);

  useImperativeHandle(ref, () => ({
    saveXML: async () => {
      if (!modeler) throw new Error('Modeler not ready');
      let baseline = -1;
      try {
        baseline = modeler.getActiveViewer().get('commandStack')._stackIdx as number;
      } catch {
        // No active viewer's commandStack — export still works.
      }
      const { xml: savedXml } = await modeler.saveXML({ format: true });
      return { xml: savedXml as string, baseline };
    },
    markSaved: (baseline) => {
      if (!modeler) return false;
      const savedIdx = typeof baseline === 'number' ? baseline : -1;
      savedStackIndexRef.current = savedIdx;
      let stillDirty = false;
      try {
        stillDirty = modeler.getActiveViewer().get('commandStack')._stackIdx !== savedIdx;
      } catch {
        stillDirty = false;
      }
      onDirtyChange?.(stillDirty);
      return stillDirty;
    },
  }), [modeler, onDirtyChange]);

  // Two effects, not one — see the matching comment in BpmnCanvas.tsx.
  useEffect(() => {
    if (!canvasRef.current || !panelRef.current) return undefined;

    const instance = new (DmnModeler as any)({
      container: canvasRef.current,
      keyboard: { bindTo: document },
      propertiesPanel: { parent: panelRef.current },
    });
    setModeler(instance);

    return () => instance.destroy();
  }, []);

  useEffect(() => {
    if (!modeler) return undefined;

    let detachCurrent: (() => void) | null = null;

    function attachToActiveView() {
      detachCurrent?.();
      detachCurrent = null;
      // Each dmn-js view (DRD / decision table / literal expression) is its
      // own diagram-js instance with its own eventBus — the top-level
      // Modeler's own .on() does not see a view's commandStack.changed, so
      // this attaches to the active *viewer* directly, not the Modeler.
      let viewer: any;
      let commandStack: any;
      try {
        viewer = modeler.getActiveViewer();
        commandStack = viewer.get('commandStack');
      } catch {
        return;
      }
      savedStackIndexRef.current = commandStack._stackIdx;
      const checkDirty = () => onDirtyChange?.(commandStack._stackIdx !== savedStackIndexRef.current);
      viewer.on('commandStack.changed', checkDirty);
      detachCurrent = () => viewer.off('commandStack.changed', checkDirty);
    }

    modeler
      .importXML(xml)
      .then(() => {
        setError(null);
        onDirtyChange?.(false);
        attachToActiveView();
        modeler.on('views.changed', attachToActiveView);
        try {
          modeler.getActiveViewer().get('canvas').zoom('fit-viewport', 'auto');
        } catch (zoomErr) {
          console.warn('zoom-to-fit failed (cosmetic only):', zoomErr);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to render diagram');
      });

    return () => {
      detachCurrent?.();
      modeler.off('views.changed', attachToActiveView);
    };
  }, [modeler, xml, onDirtyChange]);

  return (
    <div className="relative flex size-full">
      {error ? (
        <p className="absolute inset-x-0 top-0 z-10 p-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div ref={canvasRef} className="min-w-0 flex-1" />
      <div ref={panelRef} className="w-80 flex-none overflow-y-auto border-l border-border" />
    </div>
  );
});
