import { useEffect, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import ProcessBreadcrumb from '../components/ProcessBreadcrumb';
import ProcessGroupForm from '../components/ProcessGroupForm';
import { setPageTitle } from '../helpers';
import { ProcessGroup } from '../interfaces';
import HttpService from '../services/HttpService';

export default function ProcessGroupEdit() {
  const params = useParams();
  const [processGroup, setProcessGroup] = useState<ProcessGroup | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const setProcessGroupFromResult = (result: ProcessGroup) => {
      setProcessGroup(result);
    };

    HttpService.makeCallToBackend({
      path: `/process-groups/${params.process_group_id}`,
      successCallback: setProcessGroupFromResult,
    });
  }, [params.process_group_id]);

  useEffect(() => {
    if (processGroup) {
      setPageTitle([
        t('editing_process_group', { name: processGroup.display_name }),
      ]);
    }
  }, [processGroup, t]);

  if (!processGroup) {
    return null;
  }

  return (
    <>
      <ProcessBreadcrumb
        hotCrumbs={[
          [t('process_groups'), '/process-groups'],
          {
            entityToExplode: processGroup,
            entityType: 'process-group',
            linkLastItem: true,
          },
        ]}
      />
      <Typography variant="h1">
        {t('edit_process_group_with_id', { id: processGroup.id })}
      </Typography>
      <Box mt={2}>
        <ProcessGroupForm
          mode="edit"
          processGroup={processGroup}
          setProcessGroup={setProcessGroup}
        />
      </Box>
    </>
  );
}
