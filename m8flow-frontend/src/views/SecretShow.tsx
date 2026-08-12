/**
 * Secret detail — clean-room form layout (not upstream's table shell).
 * Blind edit only; never calls show-value.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
import { Can } from '../contexts/Can';
import ConfirmButton from '../components/ConfirmButton';
import ProcessBreadcrumb from '../components/ProcessBreadcrumb';
import { Notification } from '../components/Notification';
import { usePermissionFetcher } from '../hooks/PermissionService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import HttpService from '../services/HttpService';
import type { PermissionsToCheck, Secret } from '../interfaces';

const HOME = '/configuration/secrets';

export default function SecretShow() {
  const { t } = useTranslation();
  const go = useNavigate();
  const { secret_identifier: keyFromRoute } = useParams();

  const [entry, setEntry] = useState<Secret | null>(null);
  const [draftOpen, setDraftOpen] = useState(false);
  const [flash, setFlash] = useState(false);

  const { targetUris } = useUriListForPermissions();
  const uri = targetUris.secretShowPath;
  const { ability, permissionsLoaded } = usePermissionFetcher({
    [uri]: ['PUT', 'DELETE', 'GET'],
  } as PermissionsToCheck);

  useEffect(() => {
    HttpService.makeCallToBackend({
      path: `/secrets/${keyFromRoute}`,
      successCallback: setEntry,
    });
  }, [keyFromRoute]);

  if (!entry || !permissionsLoaded) return null;

  const crumbs = [
    [t('configuration'), '/configuration'],
    [t('secrets'), HOME],
    [entry.key],
  ];

  return (
    <Box>
      {flash ? (
        <Notification title={t('secret_updated')} onClose={() => setFlash(false)} />
      ) : null}
      <ProcessBreadcrumb hotCrumbs={crumbs} />
      <Typography variant="h4" component="h1" gutterBottom>
        {t('secret_key')}: {entry.key}
      </Typography>

      <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
        <Can I="DELETE" a={uri} ability={ability}>
          <ConfirmButton
            description={t('delete_secret_confirmation')}
            buttonLabel={t('delete')}
            onConfirmation={() =>
              HttpService.makeCallToBackend({
                path: `/secrets/${entry.key}`,
                httpMethod: 'DELETE',
                successCallback: () => go(HOME),
              })
            }
          />
        </Can>
        <Can I="PUT" a={uri} ability={ability}>
          <Button
            disabled={draftOpen}
            variant="contained"
            color="warning"
            onClick={() => setDraftOpen(true)}
          >
            {t('edit_secret_value')}
          </Button>
        </Can>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('key')}: {keyFromRoute}
      </Typography>

      {draftOpen ? (
        <Stack spacing={2} maxWidth={480}>
          <TextField
            id="secret_value"
            name="secret_value"
            label={t('secret_value')}
            aria-label={t('secret_value')}
            value={entry.value ?? ''}
            disabled={!ability.can('PUT', uri)}
            onChange={(e) => setEntry({ ...entry, value: e.target.value })}
          />
          <Can I="PUT" a={uri} ability={ability}>
            <Button
              variant="contained"
              color="warning"
              onClick={() =>
                HttpService.makeCallToBackend({
                  path: `/secrets/${entry.key}`,
                  httpMethod: 'PUT',
                  postBody: { value: entry.value },
                  successCallback: () => setFlash(true),
                })
              }
            >
              {t('update_value_button')}
            </Button>
          </Can>
        </Stack>
      ) : null}
    </Box>
  );
}
