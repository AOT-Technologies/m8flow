import { useEffect, useState } from 'react';
import { FolderArchive } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '@/lib/api';
import { downloadBlob } from '@/lib/download';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { exportTemplate, fetchTemplate, fetchTemplateVersions, type Template } from '@/lib/templatesApi';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { CreateProcessModelFromTemplateDialog } from './components/CreateProcessModelFromTemplateDialog';
import { TemplateDetailsPanel } from './components/TemplateDetailsPanel';
import { TemplateFileList } from './components/TemplateFileList';
import { TemplateVersionSelector } from './components/TemplateVersionSelector';

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
 * Template detail — identity, publish/visibility, and the file list.
 * Per-file authoring lives at `/templates/:id/modeler/:fileName`
 * (Templates to 100%, ticket 07).
 */
export default function TemplateModelerPage() {
  const { templateId: templateIdParam } = useParams<{ templateId: string }>();
  const { scopedTenantId, isSuperAdmin, needsTenant } = useActiveTenant();
  const { canManageProcesses } = useCapabilities();
  // Template metadata mutate stays SA-blocked; create-from-template is M8F-479.
  const canManage = Boolean(canManageProcesses) && !isSuperAdmin;
  const canCreateProcessModel = Boolean(canManageProcesses) && !needsTenant;
  const navigate = useNavigate();

  const parsedId = templateIdParam ? Number(templateIdParam) : NaN;
  const validId = Number.isFinite(parsedId);

  const [template, setTemplate] = useState<Template | null>(null);
  const [versions, setVersions] = useState<Template[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [loading, setLoading] = useState(validId);
  const [notFound, setNotFound] = useState(!validId);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    if (!validId) {
      setTemplate(null);
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchTemplate(parsedId, { includeContents: false })
      .then((tpl) => {
        if (cancelled) return;
        setTemplate(tpl);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTemplate(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load template');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [parsedId, validId]);

  useEffect(() => {
    if (!template?.templateKey) {
      setVersions([]);
      return undefined;
    }

    let cancelled = false;
    setVersionsLoading(true);
    fetchTemplateVersions(template.templateKey, { tenantId: scopedTenantId })
      .then((rows) => {
        if (!cancelled) setVersions(rows);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      })
      .finally(() => {
        if (!cancelled) setVersionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [template?.templateKey, scopedTenantId]);

  async function handleExport() {
    if (!template) return;
    const blob = await exportTemplate(template.id);
    downloadBlob(`${template.templateKey}-v${template.version}.zip`, blob);
  }

  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <header className="flex flex-none items-center justify-between gap-3 border-b border-border px-6 py-3">
        <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
          <Breadcrumbs
            items={[
              { label: 'Templates', href: '/templates' },
              { label: template?.name ?? templateIdParam ?? '' },
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
        <Button
          type="button"
          variant="pill-outline"
          size="pill"
          onClick={() => void handleExport()}
          disabled={!template}
          className="gap-1.5"
        >
          <FolderArchive className="size-3.5" strokeWidth={2.2} />
          Export
        </Button>
      </header>

      {!validId || notFound ? (
        <p className="p-6 text-sm text-muted-foreground" role="status">
          Template not found.
        </p>
      ) : loading ? (
        <p className="p-6 text-sm text-muted-foreground" aria-busy="true">
          Loading template…
        </p>
      ) : error ? (
        <p className="p-6 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : template ? (
        <>
          <TemplateVersionSelector
            current={template}
            versions={versions}
            loading={versionsLoading}
            onSelect={(id) => navigate(`/templates/${id}`)}
          />
          <TemplateDetailsPanel
            template={template}
            canManage={canManage}
            canCreateProcessModel={canCreateProcessModel}
            onTemplateChange={setTemplate}
            onCreateProcessModel={() => setCreateOpen(true)}
          />
          <TemplateFileList template={template} />
        </>
      ) : null}

      {template && createOpen ? (
        <CreateProcessModelFromTemplateDialog
          template={template}
          open
          onClose={() => setCreateOpen(false)}
          scopedTenantId={scopedTenantId}
          needsTenant={needsTenant}
          onCreated={(encodedProcessModelId) => {
            setCreateOpen(false);
            navigate(`/processes/${encodedProcessModelId}`);
          }}
        />
      ) : null}
    </div>
  );
}
