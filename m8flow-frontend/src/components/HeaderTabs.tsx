/**
 * Homepage header tabs — SA / permission-aware tab set.
 */
import { Stack, Tab, Tabs } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { usePermissionFetcher } from '../hooks/PermissionService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import UserService from '../services/UserService';

type Props = {
  value: number;
  onChange: (event: React.SyntheticEvent, next: number) => void;
  taskControlElement: React.ReactNode;
};

export default function HeaderTabs({
  value,
  onChange,
  taskControlElement,
}: Props) {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const listUri = targetUris.processInstanceListForMePath;
  const { ability, permissionsLoaded } = usePermissionFetcher({
    [listUri]: ['POST'],
  });

  if (!permissionsLoaded) return null;

  const sa = UserService.isSuperAdmin();
  const items = [
    {
      label: sa ? t('tasks') : t('tasks_assigned_to_me'),
      testId: 'tab-tasks-assigned-to-me',
    },
  ];
  if (!sa && ability.can('POST', listUri)) {
    items.push({
      label: t('workflows_created_by_me'),
      testId: 'tab-workflows-created-by-me',
    });
  }

  return (
    <Stack
      direction="row"
      alignItems="center"
      justifyContent="space-between"
      sx={{
        mb: 2,
        borderBottom: (theme) => `2px solid ${theme.palette.borders?.table ?? theme.palette.divider}`,
      }}
    >
      <Tabs
        value={value}
        onChange={onChange}
        TabIndicatorProps={{ style: { height: 3 } }}
        sx={{ flex: 1 }}
      >
        {items.map((item) => (
          <Tab
            key={item.testId}
            label={item.label}
            data-testid={item.testId}
            sx={{ textTransform: 'none' }}
          />
        ))}
      </Tabs>
      {taskControlElement}
    </Stack>
  );
}
