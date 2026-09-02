import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Alert, Button, TextField, Stack, TextareaAutosize, InputLabel } from '@mui/material';
import { modifyProcessIdentifierForPathParam, slugifyString } from '../helpers';
import HttpService from '../services/HttpService';
import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import { ProcessGroup } from '../interfaces';

type OwnProps = {
  mode: string;
  processGroup: ProcessGroup;
  setProcessGroup: (..._args: any[]) => any;
};

export default function ProcessGroupForm({ mode, processGroup, setProcessGroup }: OwnProps) {
  const [identifierInvalid, setIdentifierInvalid] = useState(false);
  const [idHasBeenUpdatedByUser, setIdHasBeenUpdatedByUser] = useState(false);
  const [displayNameInvalid, setDisplayNameInvalid] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { selectedTenantId } = useGlobalTenant();
  const requiresTenant = mode === 'new' && UserService.isSuperAdmin();
  const missingTenant = requiresTenant && !selectedTenantId;
  let newProcessGroupId = processGroup.id;

  const hasValidIdentifier = (value: string) =>
    Boolean(value.match(/^[a-z0-9][0-9a-z.-]*[a-z0-9]$/));

  const submit = (event: any) => {
    event.preventDefault();
    const parentGroupId = new URLSearchParams(document.location.search).get('parentGroupId');
    let hasErrors = missingTenant;
    if (mode === 'new' && !hasValidIdentifier(processGroup.id)) {
      setIdentifierInvalid(true);
      hasErrors = true;
    }
    if (processGroup.display_name === '') {
      setDisplayNameInvalid(true);
      hasErrors = true;
    }
    if (hasErrors) return;

    const postBody: Record<string, unknown> = {
      display_name: processGroup.display_name,
      description: processGroup.description,
      messages: processGroup.messages,
    };
    if (mode === 'new') {
      newProcessGroupId = parentGroupId ? `${parentGroupId}/${processGroup.id}` : processGroup.id;
      postBody.id = newProcessGroupId;
      postBody.m8f_tenant_id = selectedTenantId;
    }
    HttpService.makeCallToBackend({
      path: mode === 'edit'
        ? `/process-groups/${modifyProcessIdentifierForPathParam(processGroup.id)}`
        : '/process-groups',
      successCallback: () => {
        if (newProcessGroupId) navigate(`/process-groups/${modifyProcessIdentifierForPathParam(newProcessGroupId)}`);
      },
      httpMethod: mode === 'edit' ? 'PUT' : 'POST',
      postBody,
      tenantId: selectedTenantId || undefined,
    });
  };

  const update = (values: Record<string, unknown>) =>
    setProcessGroup({ ...processGroup, ...values });

  return (
    <form onSubmit={submit}>
      <Stack spacing={2}>
        {missingTenant ? (
          <Alert severity="warning" data-testid="super-admin-tenant-alert">
            {t('select_tenant_before_workflow_management')}
          </Alert>
        ) : null}
        <TextField
          id="process-group-display-name"
          data-testid="process-group-display-name-input"
          name="display_name"
          error={displayNameInvalid}
          helperText={displayNameInvalid ? t('display_name_required') : ''}
          label={t('display_name_required_label')}
          value={processGroup.display_name}
          onChange={(event) => {
            setDisplayNameInvalid(false);
            update({ display_name: event.target.value, ...(!idHasBeenUpdatedByUser && mode === 'new' ? { id: slugifyString(event.target.value) } : {}) });
          }}
        />
        {mode === 'new' ? (
          <TextField
            id="process-group-identifier"
            name="id"
            error={identifierInvalid}
            helperText={identifierInvalid ? t('identifier_requirements') : ''}
            label={t('identifier_required')}
            value={processGroup.id}
            onChange={(event) => {
              update({ id: event.target.value });
              setIdentifierInvalid(false);
              setIdHasBeenUpdatedByUser(true);
            }}
          />
        ) : null}
        <InputLabel id="data-store-description-label">{t('description')}:</InputLabel>
        <TextareaAutosize
          id="process-group-description"
          minRows={5}
          name="description"
          placeholder={t('description_placeholder')}
          value={processGroup.description || ''}
          onChange={(event) => update({ description: event.target.value })}
        />
        <Button type="submit" variant="contained" disabled={missingTenant}>{t('submit')}</Button>
      </Stack>
    </form>
  );
}
