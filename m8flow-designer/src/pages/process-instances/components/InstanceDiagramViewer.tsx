import { useEffect, useRef, useState } from 'react';
import NavigatedViewer, { applyTaskStateMarkers } from 'm8flow-bpmn/lib/NavigatedViewer';
import type { ProcessInstanceTaskState } from '@/lib/processInstancesApi';

export type InstanceDiagramViewerProps = {
  xml: string;
  tasks: ProcessInstanceTaskState[];
  onElementClick?: (bpmnIdentifier: string) => void;
};

/**
 * Thin React host shell around `m8flow-bpmn/lib/NavigatedViewer`.
 * Engine, chrome, zoom, and task-state legend live in the package.
 */
export function InstanceDiagramViewer({ xml, tasks, onElementClick }: InstanceDiagramViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewer, setViewer] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const instance = new (NavigatedViewer as any)({
      container: containerRef.current,
    });
    setViewer(instance);
    return () => instance.destroy();
  }, []);

  useEffect(() => {
    if (!viewer) return undefined;
    let cancelled = false;

    viewer
      .importXML(xml)
      .then(() => {
        if (cancelled) return;
        setError(null);
        try {
          viewer.get('canvas').zoom('fit-viewport', 'auto');
        } catch {
          /* cosmetic */
        }
        applyTaskStateMarkers(viewer, tasks);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [viewer, xml, tasks]);

  useEffect(() => {
    if (!viewer || !onElementClick) return undefined;
    const eventBus = viewer.get('eventBus');
    // An external label is its own element (`<id>_label`); report its owner.
    const handler = (event: { element: { id: string; labelTarget?: { id: string } } }) =>
      onElementClick(event.element.labelTarget?.id ?? event.element.id);
    eventBus.on('element.click', handler);
    return () => eventBus.off('element.click', handler);
  }, [viewer, onElementClick]);

  return (
    <div className="relative size-full">
      {error ? (
        <p className="absolute inset-x-0 top-0 z-10 p-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div ref={containerRef} className="size-full" />
    </div>
  );
}
