import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { ApiError, copyProcessModel, createProcessModelFile, createScriptUnitTest, deleteProcessModelFile, fetchProcessModelDetail, fetchScriptUnitTests, runProcessModelTests, runScriptUnitTest, startProcessInstance, updateProcessModel, type ProcessModelDetail } from '@/lib/api';
import { ProcessModelOverview } from './components/ProcessModelOverview';
import { Button } from '@/components/ui/button';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { ChevronLeft } from 'lucide-react';

/**
 * Process-model overview. Fetches GET /v1.0/m8flow/process-models/{id}
 * and renders the mockup layout. Route ids use `:` for `/`.
 */
export default function ProcessModelDetailPage() {
  const { processModelId } = useParams<{ processModelId: string }>();
  const { scopedTenantId, isSuperAdmin, needsTenantForWrite } = useActiveTenant();
  // canManageProcesses covers catalog writes; the publish lifecycle gates on
  // canManageProcessModels instead (M8F-508) — see ProcessesPage.
  const { canManageProcesses, canManageProcessModels, canStartProcesses } = useCapabilities();
  const [searchParams] = useSearchParams();
  // Under All Tenants the Processes list links carry the model's own tenant
  // (model ids collide across tenants), so a model opened from the list
  // resolves to exactly one tenant and behaves as if it were selected.
  const tenantId = searchParams.get('tenantId') || scopedTenantId;
  // M8F-479: catalog writes allowed for SA with a concrete tenant. A regular
  // user has no sidebar scope at all (their tenant is the cookie), so gate on
  // the super-admin write flag -- satisfied here by an explicit ?tenantId.
  const needsTenantToWrite = needsTenantForWrite && !searchParams.get('tenantId');
  const canManageCatalog = Boolean(canManageProcesses) && !needsTenantToWrite;
  // Template create remains SA-blocked server-side.
  const canSaveAsTemplate = Boolean(canManageProcesses) && !isSuperAdmin;
  // Starting an instance is a write: it must land in one tenant.
  const canStart = Boolean(canStartProcesses) && !needsTenantToWrite;
  const navigate = useNavigate();
  const modifiedId = processModelId ?? '';

  const [detail, setDetail] = useState<ProcessModelDetail | null>(null);
  const [loading, setLoading] = useState(Boolean(modifiedId));
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!modifiedId) {
      setDetail(null);
      setLoading(false);
      setNotFound(true);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchProcessModelDetail(modifiedId, tenantId)
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
  }, [modifiedId, tenantId]);

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
        tenantId={tenantId}
        canManage={canManageCatalog}
        onUpdateIdentity={
          canManageCatalog
            ? async (patch) => {
                const identity = await updateProcessModel(modifiedId, patch, tenantId);
                setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
              }
            : undefined
        }
        onAddFile={
          canManageCatalog
            ? async (input) => {
                await createProcessModelFile(modifiedId, input, tenantId);
                setDetail(await fetchProcessModelDetail(modifiedId, tenantId));
              }
            : undefined
        }
        onDeleteFile={
          canManageCatalog
            ? async (fileName) => {
                await deleteProcessModelFile(modifiedId, fileName, tenantId);
                setDetail(await fetchProcessModelDetail(modifiedId, tenantId));
              }
            : undefined
        }
        onSetPrimary={
          canManageCatalog
            ? async (fileName) => {
                await updateProcessModel(
                  modifiedId,
                  { primary_file_name: fileName },
                  tenantId,
                );
                setDetail(await fetchProcessModelDetail(modifiedId, tenantId));
              }
            : undefined
        }
        onStart={
          canStart
            ? async () => {
                const result = await startProcessInstance(modifiedId, tenantId);
                navigate(`/process-instances/${result.id}`);
              }
            : undefined
        }
        onCopy={
          canManageCatalog
            ? async (input) => {
                const identity = await copyProcessModel(modifiedId, input, tenantId);
                navigate(`/processes/${identity.id.split('/').join(':')}`);
                return identity;
              }
            : undefined
        }
        onChangeStatus={
          canManageProcessModels && !needsTenantToWrite
            ? async (status) => {
                const identity = await updateProcessModel(modifiedId, { status }, tenantId);
                setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
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
            ? () => runProcessModelTests(modifiedId, tenantId)
            : undefined
        }
        onFetchScriptUnitTests={
          canManageCatalog
            ? () => fetchScriptUnitTests(modifiedId, tenantId)
            : undefined
        }
        onCreateScriptUnitTest={
          canManageCatalog
            ? (input) => createScriptUnitTest(modifiedId, input, tenantId)
            : undefined
        }
        onRunScriptUnitTest={
          canManageCatalog
            ? (input) => runScriptUnitTest(modifiedId, input, tenantId)
            : undefined
        }
      />
    </main>
  );
}

function ShellHeader() {
  const navigate = useNavigate();

  return (
    <div className="mb-7">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mb-1.5 rounded-full font-semibold"
        onClick={() => navigate('/processes')}
      >
        <ChevronLeft className="size-3.5" strokeWidth={2} aria-hidden />
        All processes
      </Button>
      <h1 className="font-display text-[32px] font-semibold tracking-tight">Process model</h1>
    </div>
  );
}
