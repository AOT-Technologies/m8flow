import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiError, copyProcessModel, createProcessModelFile, createScriptUnitTest, deleteProcessModelFile, fetchProcessModelDetail, fetchScriptUnitTests, runProcessModelTests, runScriptUnitTest, startProcessInstance, updateProcessModel, type ProcessModelDetail } from '@/lib/api';
import { ProcessModelOverview } from './components/ProcessModelOverview';
import { BackLink } from '@/components/library/breadcrumbs/Breadcrumbs';
import { Card } from '@/components/ui/card';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';

/**
 * Process-model overview. Fetches GET /v1.0/m8flow/process-models/{id}
 * and renders the mockup layout. Route ids use `:` for `/`.
 */
export default function ProcessModelDetailPage() {
  const { processModelId } = useParams<{ processModelId: string }>();
  const { scopedTenantId, isSuperAdmin, needsTenant } = useActiveTenant();
  const { canManageProcesses, canStartProcesses } = useCapabilities();
  // The permission-check result is folded into canManageProcesses by the
  // session provider; keep the page independent of role names.
  const canManageCatalog = Boolean(canManageProcesses) && !needsTenant;
  // Template create remains SA-blocked server-side.
  const canSaveAsTemplate = Boolean(canManageProcesses) && !isSuperAdmin;
  const canStart = Boolean(canStartProcesses);
  const navigate = useNavigate();
  const modifiedId = processModelId ?? '';

  const [detail, setDetail] = useState<ProcessModelDetail | null>(null);
  const [loading, setLoading] = useState(!needsTenant && Boolean(modifiedId));
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (needsTenant || !modifiedId) {
      setDetail(null);
      setLoading(false);
      setNotFound(!modifiedId && !needsTenant);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchProcessModelDetail(modifiedId, scopedTenantId)
      .then((payload) => {
        if (!cancelled) {
          setDetail(payload);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setDetail(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
          setError(null);
          return;
        }
        setNotFound(false);
        setError(err instanceof Error ? err.message : 'Failed to load process model');
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [modifiedId, scopedTenantId, needsTenant]);

  if (needsTenant) {
    return (
      <main className="flex-1 px-11 py-10">
        <ShellHeader />
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Choose a tenant</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Process models are tenant-scoped. Select a concrete tenant in the sidebar
            — All Tenants is not supported on Processes.
          </p>
        </Card>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="flex-1 px-11 py-10">
        <ShellHeader />
        <p className="text-sm text-muted-foreground" aria-busy="true">
          Loading process model…
        </p>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="flex-1 px-11 py-10">
        <ShellHeader />
        <p className="text-sm text-muted-foreground" role="status">
          Process model not found.
        </p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex-1 px-11 py-10">
        <ShellHeader />
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      </main>
    );
  }

  if (!detail) {
    return null;
  }

  return (
    <main className="flex-1 px-11 py-10 pb-14">
      <ProcessModelOverview
        detail={detail}
        tenantId={scopedTenantId}
        canManage={canManageCatalog}
        onUpdateIdentity={
          canManageCatalog
            ? async (patch) => {
                const identity = await updateProcessModel(modifiedId, patch, scopedTenantId);
                setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
              }
            : undefined
        }
        onAddFile={
          canManageCatalog
            ? async (input) => {
                await createProcessModelFile(modifiedId, input, scopedTenantId);
                setDetail(await fetchProcessModelDetail(modifiedId, scopedTenantId));
              }
            : undefined
        }
        onDeleteFile={
          canManageCatalog
            ? async (fileName) => {
                await deleteProcessModelFile(modifiedId, fileName, scopedTenantId);
                setDetail(await fetchProcessModelDetail(modifiedId, scopedTenantId));
              }
            : undefined
        }
        onSetPrimary={
          canManageCatalog
            ? async (fileName) => {
                await updateProcessModel(
                  modifiedId,
                  { primary_file_name: fileName },
                  scopedTenantId,
                );
                setDetail(await fetchProcessModelDetail(modifiedId, scopedTenantId));
              }
            : undefined
        }
        onStart={
          canStart
            ? async () => {
                const result = await startProcessInstance(modifiedId, scopedTenantId);
                navigate(`/process-instances/${result.id}`);
              }
            : undefined
        }
        onCopy={
          canManageCatalog
            ? async (input) => {
                const identity = await copyProcessModel(modifiedId, input, scopedTenantId);
                navigate(`/processes/${identity.id.split('/').join(':')}`);
                return identity;
              }
            : undefined
        }
        onSaveAsTemplate={
          canSaveAsTemplate
            ? (templateId) => {
                navigate(`/templates/${templateId}`);
              }
            : undefined
        }
        onRunBpmnTests={
          canManageCatalog
            ? () => runProcessModelTests(modifiedId, scopedTenantId)
            : undefined
        }
        onFetchScriptUnitTests={
          canManageCatalog
            ? () => fetchScriptUnitTests(modifiedId, scopedTenantId)
            : undefined
        }
        onCreateScriptUnitTest={
          canManageCatalog
            ? (input) => createScriptUnitTest(modifiedId, input, scopedTenantId)
            : undefined
        }
        onRunScriptUnitTest={
          canManageCatalog
            ? (input) => runScriptUnitTest(modifiedId, input, scopedTenantId)
            : undefined
        }
      />
    </main>
  );
}

function ShellHeader() {
  return (
    <div className="mb-7">
      <BackLink href="/processes" LinkComponent={RouterBackLink} className="mb-1.5">
        All processes
      </BackLink>
      <h1 className="font-display text-[32px] font-semibold tracking-tight">Process model</h1>
    </div>
  );
}

function RouterBackLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}
