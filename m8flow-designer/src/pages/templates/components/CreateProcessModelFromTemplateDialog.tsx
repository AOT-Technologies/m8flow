import { useEffect, useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  ApiError,
  createProcessGroup,
  fetchProcessGroups,
  type ProcessGroupListItem,
} from '@/lib/api';
import i18n from '@/i18n';
import { slugifyProcessModelId } from '@/lib/processModelId';
import { createProcessModelFromTemplate, type Template } from '@/lib/templatesApi';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type CreateProcessModelFromTemplateDialogProps = {
  template: Template;
  open: boolean;
  onClose: () => void;
  scopedTenantId: string | null;
  /**
   * Super-admin All-Tenants gate. Regular users are cookie-bound and may have
   * a null `scopedTenantId` without blocking create-from-template.
   */
  needsTenant?: boolean;
  /** `processModel.id` from the response, already `:`-encoded for routing. */
  onCreated: (encodedProcessModelId: string) => void;
};

/**
 * "Use template" → `POST .../create-process-model` (Template modeler map,
 * ticket 04). The backend requires an *existing* process group (it 404s
 * rather than auto-creating one — confirmed from
 * `TemplateService.create_process_model_from_template`'s own
 * `is_process_group_identifier` check), so this fetches the real group
 * list rather than accepting a freehand group id. When none exist, an
 * inline "New process group" field creates one and selects it. A plain `ui/select`
 * rather than reusing `ProcessGroupsPicker` — that component's own UX is
 * "pick a filter, dialog closes," and nesting it inside this dialog (a
 * dialog opening a dialog) for what's otherwise a single form field
 * wasn't worth the indirection.
 *
 * Super-admin must have a concrete `scopedTenantId` (M8F-479); the request
 * then sends both `?tenantId=` and body `m8f_tenant_id`.
 */
export function CreateProcessModelFromTemplateDialog({
  template,
  open,
  onClose,
  scopedTenantId,
  needsTenant = false,
  onCreated,
}: CreateProcessModelFromTemplateDialogProps) {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<ProcessGroupListItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  /** Load failure — kept apart from "zero groups" so a 403/500 never offers group create. */
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [processGroupId, setProcessGroupId] = useState('');
  const [displayName, setDisplayName] = useState(template.name);
  const [processModelId, setProcessModelId] = useState(slugifyProcessModelId(template.name));
  const [idEdited, setIdEdited] = useState(false);
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Inline 409 message under Identifier: the id is already taken in the group. */
  const [idError, setIdError] = useState<string | null>(null);
  const [newGroupName, setNewGroupName] = useState('');
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [groupError, setGroupError] = useState<string | null>(null);
  const missingTenant = needsTenant;

  useEffect(() => {
    if (!open) return undefined;
    setProcessGroupId('');
    setDisplayName(template.name);
    setProcessModelId(slugifyProcessModelId(template.name));
    setIdEdited(false);
    setDescription('');
    setError(null);
    setIdError(null);
    setNewGroupName('');
    setGroupError(null);
    setGroupsError(null);

    if (missingTenant) {
      setGroups([]);
      setGroupsLoading(false);
      return undefined;
    }

    let cancelled = false;
    setGroupsLoading(true);
    fetchProcessGroups(scopedTenantId)
      .then((rows) => {
        if (!cancelled) {
          setGroups(rows);
          if (rows.length > 0) setProcessGroupId(rows[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGroups([]);
          setGroupsError(i18n.t('templates.createDialog.groupsLoadFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) setGroupsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, template.name, scopedTenantId, missingTenant]);

  function handleDisplayNameChange(value: string) {
    setDisplayName(value);
    if (!idEdited) {
      setProcessModelId(slugifyProcessModelId(value));
      setIdError(null);
    }
  }

  /**
   * "No groups yet" escape hatch. Only reachable where the caller already
   * gates on catalog write (`canManageProcesses`), the same gate the
   * Processes page uses for group create; the backend still enforces RBAC.
   */
  async function handleCreateGroup() {
    const name = newGroupName.trim();
    const id = slugifyProcessModelId(name);
    // Gate on `missingTenant`, not `scopedTenantId`: regular users are
    // cookie-bound and legitimately have a null scopedTenantId.
    if (missingTenant || !id || creatingGroup) return;
    setCreatingGroup(true);
    setGroupError(null);
    try {
      const created = await createProcessGroup(
        { id, display_name: name, description: '' },
        scopedTenantId,
      );
      setGroups((prev) => [...prev.filter((g) => g.id !== created.id), created]);
      setProcessGroupId(created.id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setGroupError(t('templates.createDialog.groupExists'));
      } else if (err instanceof ApiError && err.status === 403) {
        setGroupError(t('templates.createDialog.groupForbidden'));
      } else {
        setGroupError(
          (err instanceof ApiError && err.serverMessage) || t('templates.createDialog.groupCreateFailed'),
        );
      }
    } finally {
      setCreatingGroup(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (missingTenant) {
      setError(t('templates.createDialog.tenantRequired'));
      return;
    }
    const submittedId = processModelId.trim();
    if (!groups.some((g) => g.id === processGroupId) || !submittedId || !displayName.trim()) return;
    setSubmitting(true);
    setError(null);
    setIdError(null);
    try {
      const result = await createProcessModelFromTemplate(template.id, {
        processGroupId,
        processModelId: submittedId,
        displayName: displayName.trim(),
        description: description.trim() || undefined,
        tenantId: scopedTenantId,
      });
      const rawId = String(result.process_model.id ?? '');
      onCreated(rawId.split('/').map(encodeURIComponent).join(':'));
    } catch (err) {
      // 409 = `<group>/<identifier>` already names a process model or group.
      // The backend only checks the identifier; display names may repeat.
      if (err instanceof ApiError && err.status === 409) {
        setIdError(t('templates.createDialog.idTaken', { id: submittedId }));
      } else if (err instanceof ApiError) {
        setError(err.serverMessage || t('templates.errors.createProcessModel'));
      } else {
        setError(t('templates.errors.createProcessModel'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('templates.createDialog.title')}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            form="create-process-model-from-template-form"
            disabled={
              submitting ||
              missingTenant ||
              !groups.some((g) => g.id === processGroupId) ||
              !processModelId.trim() ||
              !displayName.trim()
            }
          >
            {submitting ? t('templates.createDialog.creating') : t('templates.createProcessModel')}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        {t('templates.createDialog.intro', { name: template.name, version: template.version })}
      </p>
      {missingTenant ? (
        <p className="text-sm text-destructive" role="alert" data-testid="create-from-template-tenant-alert">
          {t('templates.createDialog.tenantAlert')}
        </p>
      ) : null}
      <form
        id="create-process-model-from-template-form"
        onSubmit={handleSubmit}
        noValidate
        className="flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-group" className="text-xs font-medium text-muted-foreground">
            {t('templates.createDialog.processGroup')}
          </label>
          {missingTenant ? (
            <p className="text-sm text-muted-foreground">{t('templates.createDialog.chooseTenant')}</p>
          ) : groupsLoading ? (
            <p className="text-sm text-muted-foreground">{t('templates.createDialog.loadingGroups')}</p>
          ) : groupsError ? (
            <p className="text-sm text-destructive" role="alert">
              {groupsError}
            </p>
          ) : groups.length === 0 ? (
            <div className="flex flex-col gap-2" data-testid="create-from-template-new-group">
              <p className="text-sm text-muted-foreground">{t('templates.createDialog.noGroups')}</p>
              <div className="flex gap-2">
                <Input
                  id="cpmft-group"
                  value={newGroupName}
                  onChange={(e) => {
                    setNewGroupName(e.target.value);
                    setGroupError(null);
                  }}
                  onKeyDown={(e) => {
                    // Enter would otherwise submit the outer model form.
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void handleCreateGroup();
                    }
                  }}
                  placeholder={t('templates.createDialog.newGroupName')}
                  aria-label={t('templates.createDialog.newGroupName')}
                  aria-invalid={groupError ? true : undefined}
                  aria-describedby={groupError ? 'cpmft-group-error' : undefined}
                  disabled={creatingGroup}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void handleCreateGroup()}
                  disabled={creatingGroup || !slugifyProcessModelId(newGroupName.trim())}
                >
                  <Plus className="size-3.5" aria-hidden />
                  {creatingGroup ? t('templates.createDialog.creating') : t('templates.createDialog.newGroup')}
                </Button>
              </div>
              {groupError ? (
                <p id="cpmft-group-error" className="text-sm text-destructive" role="alert">
                  {groupError}
                </p>
              ) : null}
            </div>
          ) : (
            <Select value={processGroupId} onValueChange={setProcessGroupId}>
              <SelectTrigger id="cpmft-group">
                <SelectValue placeholder={t('templates.createDialog.selectGroup')} />
              </SelectTrigger>
              <SelectContent>
                {groups.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.display_name || g.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-name" className="text-xs font-medium text-muted-foreground">
            {t('templates.createDialog.displayName')}
          </label>
          <Input
            id="cpmft-name"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            required
            disabled={missingTenant}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-id" className="text-xs font-medium text-muted-foreground">
            {t('templates.createDialog.identifier')}
          </label>
          <Input
            id="cpmft-id"
            value={processModelId}
            onChange={(e) => {
              setProcessModelId(e.target.value);
              setIdEdited(true);
              setIdError(null);
            }}
            placeholder="invoice-approval"
            disabled={missingTenant}
            aria-invalid={idError ? true : undefined}
            aria-describedby={idError ? 'cpmft-id-error' : undefined}
          />
          {idError ? (
            <p id="cpmft-id-error" className="text-sm text-destructive" role="alert">
              {idError}
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              {t('templates.createDialog.identifierHint')}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-description" className="text-xs font-medium text-muted-foreground">
            {t('common.descriptionOptional')}
          </label>
          <textarea
            id="cpmft-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            disabled={missingTenant}
            className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
