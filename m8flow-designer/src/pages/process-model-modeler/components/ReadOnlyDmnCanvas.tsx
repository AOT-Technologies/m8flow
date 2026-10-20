import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import DmnViewer from 'dmn-js/lib/Viewer';
import 'dmn-js/dist/assets/diagram-js.css';
import 'dmn-js/dist/assets/dmn-js-shared.css';
import 'dmn-js/dist/assets/dmn-js-drd.css';
import 'dmn-js/dist/assets/dmn-js-decision-table.css';
import 'dmn-js/dist/assets/dmn-js-literal-expression.css';

import i18n from '@/i18n';

export function ReadOnlyDmnCanvas({ xml }: { xml: string }) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewer, setViewer] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const instance = new (DmnViewer as any)({ container: containerRef.current });
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
          viewer.getActiveViewer().get('canvas').zoom('fit-viewport', 'auto');
        } catch {
          // Some DMN files open without a DRD canvas; rendering remains valid.
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : i18n.t('modeler.canvas.renderFailed'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [viewer, xml]);

  return (
    <div aria-label={t('modeler.canvas.readOnlyDmn')} className="relative size-full">
      {error ? (
        <p className="absolute inset-x-0 top-0 z-10 p-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div ref={containerRef} className="size-full" />
    </div>
  );
}
