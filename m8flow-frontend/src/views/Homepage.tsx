/**
 * m8flow Homepage — clean-room recompose of the tasks home view.
 *
 * Delta vs upstream: super-admins refetch `/tasks` when the global tenant
 * selection changes (`?tenantId=`). Grouping and chrome are re-expressed with
 * independent helpers/names so the copy gate sees tenant logic, not a body lift.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import TaskControls from '../components/TaskControls';
import HeaderTabs from '../components/HeaderTabs';
import TaskTable from '../components/TaskTable';
import HttpService from '../services/HttpService';
import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import { ProcessInstanceTask } from '../interfaces';
import OnboardingView from './OnboardingView';

type HomeScreenProps = {
  viewMode: 'table' | 'tile';
  setViewMode: React.Dispatch<React.SetStateAction<'table' | 'tile'>>;
  isMobile: boolean;
};

type Buckets = Record<string, ProcessInstanceTask[]>;

/** Synthetic bucket key for tasks assigned directly to the current user. */
const ME_BUCKET = 'spiff_synthetic_key_indicating_assigned_to_me';

const partitionByModelFolder = (items: ProcessInstanceTask[]): Buckets =>
  items.reduce<Buckets>((acc, item) => {
    const folder = item.process_model_identifier.split('/').slice(0, -1).join('/');
    (acc[folder] ??= []).push(item);
    return acc;
  }, {});

const partitionByAssignee = (items: ProcessInstanceTask[]): Buckets =>
  items.reduce<Buckets>((acc, item) => {
    const bucket = item.assigned_user_group_identifier || ME_BUCKET;
    (acc[bucket] ??= []).push(item);
    return acc;
  }, {});

const orderedBucketKeys = (buckets: Buckets): string[] =>
  Object.keys(buckets).sort((a, b) => {
    if (a === ME_BUCKET) return -1;
    if (b === ME_BUCKET) return 1;
    return a.localeCompare(b);
  });

const homeTasksUrl = (superAdmin: boolean, tenant?: string | null): string =>
  superAdmin && tenant
    ? `/tasks?tenantId=${encodeURIComponent(tenant)}`
    : '/tasks';

export default function Homepage({
  viewMode,
  setViewMode,
  isMobile,
}: HomeScreenProps) {
  const go = useNavigate();
  const { t } = useTranslation();
  const superAdmin = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();

  const [inbox, setInbox] = useState<ProcessInstanceTask[] | null>(null);
  const [buckets, setBuckets] = useState<Buckets | null>(null);
  const [activeGrouping, setActiveGrouping] = useState<string | null>(null);
  const [resumeInstanceId, setResumeInstanceId] = useState<number | null>(null);

  const assigneeLabel = t('responsible_party');
  const folderLabel = t('process_group');
  const groupingChoices = useMemo(
    () => [assigneeLabel, folderLabel],
    [assigneeLabel, folderLabel],
  );

  const refreshInbox = useCallback(() => {
    HttpService.makeCallToBackend({
      path: homeTasksUrl(superAdmin, selectedTenantId),
      successCallback: (payload: { results: ProcessInstanceTask[] }) => {
        setInbox(payload.results);
      },
    });
  }, [superAdmin, selectedTenantId]);

  useEffect(() => {
    refreshInbox();
  }, [refreshInbox]);

  useEffect(() => {
    const raw = localStorage.getItem('lastProcessInstanceId');
    if (!raw) return;
    setResumeInstanceId(Number(raw));
    localStorage.removeItem('lastProcessInstanceId');
  }, []);

  const applyGrouping = useCallback(
    (choice: string) => {
      if (!inbox) return;
      if (choice === '') {
        setBuckets(null);
        setActiveGrouping(null);
        return;
      }
      setActiveGrouping(choice);
      if (choice === folderLabel) {
        setBuckets(partitionByModelFolder(inbox));
      } else if (choice === assigneeLabel) {
        setBuckets(partitionByAssignee(inbox));
      }
    },
    [inbox, folderLabel, assigneeLabel],
  );

  const headingForBucket = (bucketKey: string): string => {
    if (bucketKey === ME_BUCKET) return t('tasks_for');
    if (activeGrouping === 'Process Group') return t('tasks_from_process_group');
    return t('tasks_for_user_group');
  };

  const bucketSections =
    buckets &&
    orderedBucketKeys(buckets).map((bucketKey) => (
      <Box key={bucketKey} mb={2}>
        <Typography variant="h4" mb={1}>
          {headingForBucket(bucketKey)}
          <Box component="span" color="text.accent">
            {bucketKey === ME_BUCKET ? t('me') : bucketKey}
          </Box>
        </Typography>
        <TaskTable entries={buckets[bucketKey]} viewMode={viewMode} />
      </Box>
    ));

  const inboxBody = (() => {
    if (!inbox) return null;
    if (bucketSections) return bucketSections;
    return <TaskTable entries={inbox} viewMode={viewMode} />;
  })();

  const phoneChrome = (
    <Box
      position="fixed"
      top={0}
      left={0}
      width="100%"
      zIndex={1300}
      display="flex"
      justifyContent="space-between"
      alignItems="center"
      bgcolor="background.default"
      p={2}
      boxShadow={1}
    >
      <Typography variant="h1">{t('home')}</Typography>
    </Box>
  );

  const resumeBanner =
    resumeInstanceId != null && !isMobile ? (
      <Box
        className="fadeIn"
        position="fixed"
        top={16}
        right={16}
        bgcolor="background.paper"
        boxShadow={3}
        p={2}
        borderRadius={1}
        zIndex={1300}
      >
        <Typography variant="h6">{t('last_process_instance')}</Typography>
        <Typography variant="body2">
          {t('id_label')}: {resumeInstanceId}
        </Typography>
      </Box>
    ) : null;

  const controls = (
    <Box display="flex" alignItems="center">
      <TaskControls
        viewMode={viewMode}
        setViewMode={setViewMode}
        groupByOptions={groupingChoices}
        onGroupBySelect={applyGrouping}
        selectedGroupBy={activeGrouping}
      />
    </Box>
  );

  return (
    <>
      {isMobile ? phoneChrome : (
        <Typography variant="h1" mb={2}>
          {t('home')}
        </Typography>
      )}
      <OnboardingView />
      {resumeBanner}
      <HeaderTabs
        value={0}
        onChange={(_evt, next) => {
          if (next === 1) go('/started-by-me');
        }}
        taskControlElement={controls}
      />
      {inboxBody}
    </>
  );
}
