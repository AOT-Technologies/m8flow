import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useBeforeUnload, useNavigate, useParams } from 'react-router-dom';

import { ApiError, fetchConnectorsGrouped } from '@/lib/api';
import { fetchConnectorProfilesForPicker } from '@/lib/connectorsApi';
import { downloadTextFile } from '@/lib/download';
import { useActiveTenant } from '@/components/session/hooks';
import {
  contentTypeForTemplateFileName,
  fetchTemplate,
  fetchTemplateFileContent,
  saveTemplateFileContent,
  templateModelerFilePath,
  type Template,
} from '@/lib/templatesApi';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { Pill } from '@/components/library/pill/Pill';
import { DiagramCanvas } from '@/pages/process-model-modeler/components/DiagramCanvas';
import type { DiagramCanvasHandle } from '@/pages/process-model-modeler/components/DiagramCanvasHandle';
import type { BpmnCanvasServiceTaskOperator } from '@/pages/process-model-modeler/components/BpmnCanvas';
import { ModelerFileToolbar, type ModelerSavePhase } from '@/pages/process-model-modeler/components/ModelerFileToolbar';
import { UnsavedChangesDialog } from '@/pages/process-model-modeler/components/ModelerFileDialogs';

type SavePhase = ModelerSavePhase;

const ERROR_FLASH_MS = 2500;

/** Adapter passed to `Breadcrumbs`' `LinkComponent` for client-side
 * navigation (component-adoption map, ticket 11). */
function RouterBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

/**
 * One template file in DiagramCanvas — `/templates/:id/modeler/:fileName`
 * (Templates to 100%, ticket 07). Dispatch is the process modeler's
 * (`bpmn` / `dmn` / `form` / `text`). Saving a published template forks a
 * draft; this page re-anchors on the returned id.
 */
export default function TemplateFileModelerPage() {
  const { templateId: templateIdParam, fileName: fileNameParam } = useParams<{
    templateId: string;
    fileName: string;
  }>();
  const { scopedTenantId } = useActiveTenant();
  const navigate = useNavigate();
  const canvasRef = useRef<DiagramCanvasHandle>(null);

  const parsedId = templateIdParam ? Number(templateIdParam) : NaN;
  const validId = Number.isFinite(parsedId);
  const file = fileNameParam ?? '';

  const [template, setTemplate] = useState<Template | null>(null);
  const [xml, setXml] = useState<string | null>(null);
  const [loading, setLoading] = useState(validId && Boolean(file));
  const [notFound, setNotFound] = useState(!validId || !file);
  const [error, setError] = useState<string | null>(null);
  const [savePhase, setSavePhase] = useState<SavePhase>('saved');
  const currentIdRef = useRef<number | null>(null);
  const allowLeaveRef = useRef(false);
  const [leaveTo, setLeaveTo] = useState<string | null>(null);

  useEffect(() => {
    if (!validId || !file) {
      setTemplate(null);
      setXml(null);
      setLoading(false);
      setNotFound(true);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchTemplate(parsedId, { includeContents: false })
      .then(async (tpl) => {
        if (cancelled) return;
        currentIdRef.current = tpl.id;
        const listed = (tpl.files ?? []).some((entry) => entry.fileName === file);
        if (!listed) {
          setTemplate(tpl);
          setXml(null);
          setNotFound(true);
          return;
        }
        const content = await fetchTemplateFileContent(tpl.id, file);
        if (cancelled) return;
        setTemplate(tpl);
        setXml(content);
        setSavePhase('saved');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTemplate(null);
        setXml(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load file');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [parsedId, validId, file]);

  const reanchorIfForked = useCallback(
    (updated: Template) => {
      const previous = currentIdRef.current;
      currentIdRef.current = updated.id;
      setTemplate(updated);
      if (previous != null && updated.id !== previous) {
        navigate(templateModelerFilePath(updated.id, file), { replace: true });
      }
    },
    [file, navigate],
  );

  const handleDirtyChange = useCallback((dirty: boolean) => {
    setSavePhase((phase) => {
      if (phase === 'saving' || phase === 'error') return phase;
      return dirty ? 'dirty' : 'saved';
    });
  }, []);

  const handleSave = useCallback(async () => {
    if (!canvasRef.current || currentIdRef.current == null) return;
    setSavePhase('saving');
    try {
      const { xml, baseline } = await canvasRef.current.saveXML();
      const updated = await saveTemplateFileContent(
        currentIdRef.current,
        file,
        xml,
        contentTypeForTemplateFileName(file),
      );
      const stillDirty = canvasRef.current.markSaved(baseline);
      setSavePhase(stillDirty ? 'dirty' : 'saved');
      reanchorIfForked(updated);
    } catch {
      setSavePhase('error');
      setTimeout(() => setSavePhase('dirty'), ERROR_FLASH_MS);
    }
  }, [file, reanchorIfForked]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        if (savePhase === 'dirty') {
          void handleSave();
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [savePhase, handleSave]);

  async function handleDownload() {
    if (!canvasRef.current) return;
    const { xml } = await canvasRef.current.saveXML();
    downloadTextFile(file, xml, contentTypeForTemplateFileName(file));
  }

  const handleReadFile = useCallback(
    (name: string) => fetchTemplateFileContent(currentIdRef.current ?? parsedId, name),
    [parsedId],
  );
  const handleWriteFile = useCallback(
    async (name: string, content: string) => {
      if (currentIdRef.current == null) return;
      const updated = await saveTemplateFileContent(
        currentIdRef.current,
        name,
        content,
        contentTypeForTemplateFileName(name),
      );
      reanchorIfForked(updated);
    },
    [reanchorIfForked],
  );
  const handleFormFilesChanged = useCallback(() => {
    const id = currentIdRef.current;
    if (id == null) return;
    void fetchTemplate(id)
      .then((updated) => setTemplate(updated))
      .catch(() => {});
  }, []);
  const handleLaunchDmnEditor = useCallback(
    (name: string) => {
      const id = currentIdRef.current ?? parsedId;
      navigate(templateModelerFilePath(id, name));
    },
    [navigate, parsedId],
  );
  const handleFetchServiceTaskOperators = useCallback(async (): Promise<BpmnCanvasServiceTaskOperator[]> => {
    const groups = await fetchConnectorsGrouped();
    return groups.flatMap((group) =>
      group.operations.map((operation) => ({ id: operation.id, parameters: operation.parameters })),
    );
  }, []);
  const handleFetchConnectorProfiles = useCallback(
    (connectorType: string) => fetchConnectorProfilesForPicker(connectorType, scopedTenantId),
    [scopedTenantId],
  );

  const fileLower = file.toLowerCase();
  const isBpmn = fileLower.endsWith('.bpmn');
  const isDiagram = isBpmn || fileLower.endsWith('.dmn');

  const dirty = savePhase === 'dirty';
  useBeforeUnload(
    useCallback(
      (event) => {
        if (dirty) event.preventDefault();
      },
      [dirty],
    ),
  );
  useEffect(() => {
    if (!dirty) return undefined;
    function onClick(event: MouseEvent) {
      if (allowLeaveRef.current || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest('a[href]');
      if (!(anchor instanceof HTMLAnchorElement)) return;
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      const url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      event.preventDefault();
      event.stopPropagation();
      setLeaveTo(`${url.pathname}${url.search}${url.hash}`);
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [dirty]);

  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <header className="flex flex-none items-center justify-between gap-3 border-b border-border px-6 py-3">
        <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
          <Breadcrumbs
            items={[
              { label: 'Templates', href: '/templates' },
              {
                label: template?.name ?? templateIdParam ?? '',
                href: validId ? `/templates/${parsedId}` : '/templates',
              },
              { label: file },
            ]}
            LinkComponent={RouterBreadcrumbLink}
            linkClassName="text-info font-normal"
            lastClassName="min-w-0 truncate font-mono"
            className="min-w-0 text-muted-foreground"
          />
          {template ? (
            <Pill tone={template.isPublished ? 'success' : 'muted'} dot={false} className="shrink-0">
              {template.isPublished ? 'Published' : 'Draft'} · v{template.version}
            </Pill>
          ) : null}
        </div>
        <ModelerFileToolbar
          savePhase={savePhase}
          fileLoaded={xml != null}
          canManage={false}
          isPrimary={isBpmn}
          isBpmn={isBpmn}
          isDiagram={isDiagram}
          onSave={() => void handleSave()}
          onDownload={() => void handleDownload()}
          onViewXml={undefined}
        />
      </header>

      <main className="min-h-0 flex-1">
        {notFound ? (
          <p className="p-6 text-sm text-muted-foreground" role="status">
            File not found.
          </p>
        ) : loading ? (
          <p className="p-6 text-sm text-muted-foreground" aria-busy="true">
            Loading file…
          </p>
        ) : error ? (
          <p className="p-6 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : xml != null ? (
          <DiagramCanvas
            ref={canvasRef}
            fileName={file}
            xml={xml}
            onDirtyChange={handleDirtyChange}
            files={template?.files.map((entry) => ({ name: entry.fileName })) ?? []}
            onReadFile={handleReadFile}
            onWriteFile={handleWriteFile}
            onCreateFile={handleWriteFile}
            onFilesChanged={handleFormFilesChanged}
            onLaunchDmnEditor={handleLaunchDmnEditor}
            onFetchServiceTaskOperators={handleFetchServiceTaskOperators}
            onFetchConnectorProfiles={handleFetchConnectorProfiles}
          />
        ) : null}
      </main>
      <UnsavedChangesDialog
        open={leaveTo != null}
        onStay={() => setLeaveTo(null)}
        onLeave={() => {
          const to = leaveTo;
          allowLeaveRef.current = true;
          setLeaveTo(null);
          if (to) navigate(to);
        }}
      />
    </div>
  );
}
