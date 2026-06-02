/**
 * Override: ProcessGroupCard
 *
 * Adds a tenant-name chip on the card when the current user is a super-admin
 * and the API response included a tenantName for this group.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import { useNavigate } from 'react-router';
import { Subject } from 'rxjs';
import UserService from '../../services/UserService';

export default function ProcessGroupCard({
  group,
  stream,
  navigateToPage = false,
}: {
  group: Record<string, any>;
  stream?: Subject<Record<string, any>>;
  navigateToPage?: boolean;
}) {
  const navigate = useNavigate();
  const captionColor = 'text.secondary';
  const { t } = useTranslation();
  const isSuperAdmin = UserService.isSuperAdmin();
  const tenantName: string | undefined = group.tenantName;

  return (
    <Card
      elevation={0}
      sx={{
        padding: 2,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        position: 'relative',
        border: '1px solid',
        borderColor: 'borders.primary',
        borderRadius: 2,
        ':hover': {
          backgroundColor: 'background.bluegreylight',
        },
      }}
      onClick={() => {
        if (stream) {
          stream.next(group);
        }
        if (navigateToPage) {
          navigate(`/process-groups/${group.id.replaceAll('/', ':')}`);
        }
      }}
    >
      <CardActionArea>
        <CardContent>
          <Stack>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              gap={1}
            >
              <Typography variant="body1" sx={{ fontWeight: 700 }}>
                {group.display_name}
              </Typography>
              {isSuperAdmin && tenantName && (
                <Chip
                  size="small"
                  label={tenantName}
                  data-testid={`process-group-tenant-chip-${group.id}`}
                />
              )}
            </Stack>

            <Typography
              variant="caption"
              sx={{ fontWeight: 700, color: 'text.secondary' }}
            >
              {group.description || '--'}
            </Typography>

            <Typography variant="caption" sx={{ color: captionColor }}>
              {`${t('groups')}: ${group.process_groups?.length ?? 0}`}
            </Typography>
            <Typography variant="caption" sx={{ color: captionColor }}>
              {`${t('models')}: ${group.process_models?.length ?? 0}`}
            </Typography>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
