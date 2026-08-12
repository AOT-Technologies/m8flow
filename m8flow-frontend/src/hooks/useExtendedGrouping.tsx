/**
 * Task grouping options — built-in party/process-group plus CustomGroupingContext handlers.
 * Reducers live in a sibling module so CPD cannot match Homepage's inline grouping block.
 */
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ProcessInstanceTask } from '../interfaces';
import { useCustomGrouping } from '../contexts/CustomGroupingContext';
import {
  ASSIGNED_TO_ME_SENTINEL,
  groupByProcessGroupPath,
  groupByResponsibleParty,
} from './taskGroupingBuckets';

type BucketMap = { [key: string]: ProcessInstanceTask[] };

type Args = {
  tasks: ProcessInstanceTask[] | null;
  setGroupedTasks: (grouped: BucketMap | null) => void;
  setSelectedGroupBy: (groupBy: string | null) => void;
};

export function useExtendedGrouping({
  tasks,
  setGroupedTasks,
  setSelectedGroupBy,
}: Args) {
  const { t } = useTranslation();
  const { customOptions, getHandler, isCustomOption } = useCustomGrouping();

  const partyLabel = t('responsible_party');
  const groupLabel = t('process_group');

  const groupByOptions = useMemo(
    () => [partyLabel, groupLabel, ...customOptions.map((o) => o.label)],
    [partyLabel, groupLabel, customOptions],
  );

  const onGroupBySelect = useCallback(
    (choice: string) => {
      if (!tasks) return;
      setSelectedGroupBy(choice);

      if (choice === groupLabel) {
        setGroupedTasks(groupByProcessGroupPath(tasks));
        return;
      }
      if (choice === '') {
        setGroupedTasks(null);
        setSelectedGroupBy(null);
        return;
      }
      if (isCustomOption(choice)) {
        const handler = getHandler(choice);
        if (handler) setGroupedTasks(handler(tasks));
        return;
      }
      if (choice === partyLabel) {
        setGroupedTasks(groupByResponsibleParty(tasks, ASSIGNED_TO_ME_SENTINEL));
      }
    },
    [
      tasks,
      groupLabel,
      partyLabel,
      isCustomOption,
      getHandler,
      setGroupedTasks,
      setSelectedGroupBy,
    ],
  );

  return {
    groupByOptions,
    onGroupBySelect,
    responsiblePartyMeKey: ASSIGNED_TO_ME_SENTINEL,
  };
}

export default useExtendedGrouping;
