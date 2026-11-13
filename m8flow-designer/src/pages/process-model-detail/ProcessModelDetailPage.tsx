import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError, copyProcessModel, createProcessModelFile, createScriptUnitTest, deleteProcessModelFile, fetchProcessModelDetail, fetchScriptUnitTests, runProcessModelTests, runScriptUnitTest, startProcessInstance, updateProcessModel, type ProcessModelDetail } from '@/lib/api';
import { ProcessModelOverview } from './components/ProcessModelOverview';
import { ProcessModelVersionHistory } from './components/ProcessModelVersionHistory';
import { useProcessModelVersionPermissions } from './components/useProcessModelVersionPermissions';
import { publishProcessModel } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { ChevronLeft } from 'lucide-react';
import i18n from '@/i18n';

/**
 * Process-model overview. Fetches GET /v1.0/m8flow/process-models/{id}
 * and renders the mockup layout. Route ids use `:` for `/`.
 */
export default function ProcessModelDetailPage() {
  const { t } = useTranslation();
  const { processModelId } = useParams<{ processModelId: string }>();
  const { scopedTenantId, isSuperAdmin, needsTenantForWrite } = useActiveTenant();
  const {
    canManageProcessModels,
    canStartProcesses,
    canCreateTemplates,
    canCopyProcessModels,
    canRunProcessModelTests,
    canCreateScriptUnitTests,
    canRunScriptUnitTests,
    canCreateProcessModelFiles,
    canDeleteProcessModelFiles,
    canReadProcessModelFiles,
  } = useCapabilities();
  const [searchParams] = useSearchParams();
  // Under All Tenants the Processes list links carry the model's own tenant
  // (model ids collide across tenants), so a model opened from the list
  // resolves to exactly one tenant and behaves as if it were selected.
  const tenantId = searchParams.get('tenantId') || scopedTenantId;
  // M8F-479: catalog writes allowed for SA with a concrete tenant. A regular
  // user has no sidebar scope at all (their tenant is the cookie), so gate on
  // the super-admin write flag -- satisfied here by an explicit ?tenantId.
  const needsTenantToWrite = needsTenantForWrite && !searchParams.get('tenantId');
  const canEditModel = canManageProcessModels && !needsTenantToWrite;
  const canCreateModelFile = canCreateProcessModelFiles && !needsTenantToWrite;
  const canDeleteModelFile = canDeleteProcessModelFiles && !needsTenantToWrite;
  const canCopyModel = canCopyProcessModels && !needsTenantToWrite;
  const canRunBpmnTests = canRunProcessModelTests && !needsTenantToWrite;
  const canCreateScriptTest = canCreateScriptUnitTests && !needsTenantToWrite;
  const canRunScriptTest = canRunScriptUnitTests && !needsTenantToWrite;
  // Template creation remains read-only for super-admins in the backend service.
  const canSaveAsTemplate = canCreateTemplates && !isSuperAdmin && !needsTenantToWrite;
  // Starting an instance is a write: it must land in one tenant.
  const navigate = useNavigate();
  const modifiedId = processModelId ?? '';

  const [detail, setDetail] = useState<ProcessModelDetail | null>(null);
  const versionPermissions = useProcessModelVersionPermissions(modifiedId, tenantId, Boolean(detail?.working_revision));
  const canStart = (detail?.working_revision ? versionPermissions?.start : canStartProcesses) && !needsTenantToWrite;
  const [loading, setLoading] = useState(Boolean(modifiedId));
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versionFeedback, setVersionFeedback] = useState('');

  useEffect(() => {
    setVersionFeedback('');
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
        setError(err instanceof Error ? err.message : i18n.t('processModelDetail.page.loadFailed'));
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
          {t('processModelDetail.page.loading')}
        </p>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="flex-1 px-11 py-10">
        <ShellHeader />
        <p className="text-sm text-muted-foreground" role="status">
          {t('processModelDetail.page.notFound')}
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
    <main className="min-w-0 flex-1 px-5 py-10 pb-14 sm:px-11">
      <ProcessModelOverview
        detail={detail}
        tenantId={tenantId}
        canManage={canEditModel}
        canReadFiles={canReadProcessModelFiles}
        versionFeedback={versionFeedback}
        versionHistory={versionPermissions?.history && (
          <ProcessModelVersionHistory
            key={`${detail.tenant_id}/${modifiedId}`}
            modifiedId={modifiedId}
            tenantId={tenantId || (isSuperAdmin ? detail.tenant_id : undefined)}
            revision={detail.working_revision}
            canRestore={Boolean(versionPermissions.restore && !needsTenantToWrite)}
            triggerStyle="pill"
            onChanged={(identity, message) => {
              setVersionFeedback(message);
              setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
              void fetchProcessModelDetail(modifiedId, tenantId).then(setDetail).catch(() => {
                setError(t('processModelDetail.page.loadFailed'));
              });
            }}
          />
        )}
        onPublish={versionPermissions?.publish && !needsTenantToWrite && detail.working_revision
          ? async () => {
              const identity = await publishProcessModel(modifiedId, detail.working_revision!, tenantId);
              setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
            }
          : undefined}
        onUpdateIdentity={
          canEditModel
            ? async (patch) => {
                const identity = await updateProcessModel(modifiedId, patch, tenantId, detail.working_revision);
                setDetail((prev) => (prev ? { ...prev, ...identity } : prev));
              }
            : undefined
        }
        onAddFile={
          canCreateModelFile
            ? async (input) => {
                await createProcessModelFile(modifiedId, input, tenantId, detail.working_revision);
                setDetail(await fetchProcessModelDetail(modifiedId, tenantId));
              }
            : undefined
        }
        onDeleteFile={
          canDeleteModelFile
            ? async (fileName) => {
                await deleteProcessModelFile(modifiedId, fileName, tenantId, detail.working_revision);
                setDetail(await fetchProcessModelDetail(modifiedId, tenantId));
              }
            : undefined
        }
        onSetPrimary={
          canEditModel
            ? async (fileName) => {
                await updateProcessModel(
                  modifiedId,
                  { primary_file_name: fileName },
                  tenantId,
                  detail.working_revision,
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
          canCopyModel
            ? async (input) => {
                const identity = await copyProcessModel(modifiedId, input, tenantId);
                navigate(`/processes/${identity.id.split('/').join(':')}`);
                return identity;
              }
            : undefined
        }
        onChangeStatus={
          canEditModel
            ? async (status) => {
                const identity = await updateProcessModel(modifiedId, { status }, tenantId, detail.working_revision);
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
          canRunBpmnTests
            ? () => runProcessModelTests(modifiedId, tenantId)
            : undefined
        }
        onFetchScriptUnitTests={
          (canCreateScriptTest || canRunScriptTest)
            ? () => fetchScriptUnitTests(modifiedId, tenantId)
            : undefined
        }
        onCreateScriptUnitTest={
          canCreateScriptTest
            ? async (input) => {
                const result = await createScriptUnitTest(modifiedId, input, tenantId, detail.working_revision);
                if (result.working_revision) {
                  setDetail((prev) => prev && ({
                    ...prev,
                    working_revision: result.working_revision,
                    draft_version: result.draft_version,
                    published_version: result.published_version,
                    has_unpublished_changes: result.has_unpublished_changes,
                  }));
                }
                return result;
              }
            : undefined
        }
        onRunScriptUnitTest={
          canRunScriptTest
            ? (input) => runScriptUnitTest(modifiedId, input, tenantId)
            : undefined
        }
      />
    </main>
  );
}

function ShellHeader() {
  const { t } = useTranslation();
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
        {t('processModelDetail.allProcesses')}
      </Button>
      <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('processModelDetail.page.title')}</h1>
    </div>
  );
}
