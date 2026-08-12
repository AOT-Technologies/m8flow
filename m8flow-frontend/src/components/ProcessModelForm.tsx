/**
 * m8flow ProcessModelForm — clean-room create/edit form.
 *
 * Delta vs upstream: on create, super-admins must pick a tenant; the POST body
 * carries `m8f_tenant_id`. Notification/metadata sections that upstream shows
 * are intentionally omitted from this product surface.
 */
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  TextField,
  Select,
  MenuItem,
  Typography,
  FormControl,
  InputLabel,
  Stack,
  Box,
} from '@mui/material';

import { modifyProcessIdentifierForPathParam, slugifyString } from '../helpers';
import HttpService from '../services/HttpService';
import TenantService from '../services/TenantService';
import UserService from '../services/UserService';
import { ProcessModel } from '../interfaces';

type ProcessModelFormProps = {
  mode: string;
  processModel: ProcessModel;
  processGroupId?: string;
  setProcessModel: (...args: any[]) => any;
};

const IDENTIFIER_RE = /^[a-z0-9][0-9a-z.-]+[a-z0-9]$/;

export default function ProcessModelForm({
  mode,
  processModel: model,
  processGroupId: groupId,
  setProcessModel: setModel,
}: ProcessModelFormProps) {
  const { t } = useTranslation();
  const go = useNavigate();

  const [badId, setBadId] = useState(false);
  const [idEdited, setIdEdited] = useState(false);
  const [badName, setBadName] = useState(false);
  const [chosenTenant, setChosenTenant] = useState('');
  const [badTenant, setBadTenant] = useState(false);

  const isCreate = mode === 'new';
  const requireTenant = isCreate && UserService.isSuperAdmin();
  const { data: tenantOptions = [], isLoading: loadingTenants } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => TenantService.getAllTenants(),
    enabled: requireTenant,
  });

  const merge = (patch: Partial<ProcessModel>) => setModel({ ...model, ...patch });

  const afterSave = (saved: ProcessModel) => {
    if (!saved?.id) return;
    go(`/process-models/${modifyProcessIdentifierForPathParam(saved.id)}`);
  };

  const handleDisplayName = (value: string) => {
    setBadName(false);
    const patch: Partial<ProcessModel> = { display_name: value };
    if (!idEdited && isCreate) patch.id = slugifyString(value);
    merge(patch);
  };

  const handleSubmit = (evt: FormEvent) => {
    evt.preventDefault();

    let failed = false;
    if (isCreate && !IDENTIFIER_RE.test(model.id)) {
      setBadId(true);
      failed = true;
    }
    if (!model.display_name) {
      setBadName(true);
      failed = true;
    }
    if (requireTenant && !chosenTenant.trim()) {
      setBadTenant(true);
      failed = true;
    }
    if (failed) return;

    const isEdit = mode === 'edit';
    const endpoint = isEdit
      ? `/process-models/${modifyProcessIdentifierForPathParam(model.id)}`
      : `/process-models/${modifyProcessIdentifierForPathParam(groupId || '')}`;

    const payload: Record<string, unknown> = {
      display_name: model.display_name,
      description: model.description,
      metadata_extraction_paths: model.metadata_extraction_paths,
      fault_or_suspend_on_exception: model.fault_or_suspend_on_exception,
      exception_notification_addresses: model.exception_notification_addresses,
    };
    if (isCreate) payload.id = `${groupId}/${model.id}`;
    if (requireTenant && chosenTenant.trim()) {
      payload.m8f_tenant_id = chosenTenant.trim();
    }

    HttpService.makeCallToBackend({
      path: endpoint,
      successCallback: afterSave,
      httpMethod: isEdit ? 'PUT' : 'POST',
      postBody: payload,
    });
  };

  return (
    <Box
      component="form"
      data-testid="process-model-form"
      onSubmit={handleSubmit}
    >
      <Stack spacing={2}>
        <TextField
          id="m8-model-display-name"
          name="display_name"
          data-testid="process-model-display-name-input"
          error={badName}
          helperText={badName ? t('display_name_required') : ''}
          label={t('display_name')}
          value={model.display_name}
          onChange={(e) => handleDisplayName(e.target.value)}
          fullWidth
        />

        {requireTenant ? (
          <FormControl fullWidth error={badTenant} disabled={loadingTenants}>
            <InputLabel id="m8-tenant-label">{t('tenant')}</InputLabel>
            <Select
              labelId="m8-tenant-label"
              id="m8-tenant-id"
              data-testid="super-admin-tenant-select"
              value={chosenTenant}
              label={t('tenant')}
              onChange={(e) => {
                const next = String(e.target.value);
                setChosenTenant(next);
                if (badTenant && next.trim()) setBadTenant(false);
              }}
            >
              <MenuItem value="">
                <em>{t('select_tenant_placeholder')}</em>
              </MenuItem>
              {tenantOptions.map((tenant) => (
                <MenuItem key={tenant.id} value={tenant.id}>
                  {tenant.name} ({tenant.slug})
                </MenuItem>
              ))}
            </Select>
            {badTenant ? (
              <Typography variant="caption" color="error" sx={{ mt: 0.5, ml: 1.5 }}>
                {t('tenant_required_for_super_admin')}
              </Typography>
            ) : null}
          </FormControl>
        ) : null}

        {isCreate ? (
          <TextField
            id="m8-model-identifier"
            name="id"
            data-testid="process-model-identifier-input"
            error={badId}
            helperText={badId ? t('identifier_validation_message') : ''}
            label={t('identifier')}
            value={model.id}
            onChange={(e) => {
              const next = e.target.value;
              merge({ id: next });
              if (badId && IDENTIFIER_RE.test(next)) setBadId(false);
              setIdEdited(true);
            }}
            fullWidth
          />
        ) : null}

        <TextField
          id="m8-model-description"
          name="description"
          data-testid="process-model-description-input"
          label={t('description')}
          value={model.description}
          onChange={(e) => merge({ description: e.target.value })}
          multiline
          fullWidth
        />

        <Box>
          <Button
            data-testid="process-model-submit-button"
            variant="contained"
            type="submit"
          >
            {t('submit')}
          </Button>
        </Box>
      </Stack>
    </Box>
  );
}
