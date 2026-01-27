/**
 * m8 Extension: Extended Grouping Hook
 * 
 * This hook extends the core grouping functionality with custom options.
 * It wraps the original grouping logic and adds support for custom grouping handlers.
 */

import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ProcessInstanceTask } from '@spiffworkflow-frontend/interfaces';
import { useCustomGrouping } from '../contexts/CustomGroupingContext';

type GroupedItems = {
  [key: string]: ProcessInstanceTask[];
};

interface UseExtendedGroupingProps {
  tasks: ProcessInstanceTask[] | null;
  setGroupedTasks: (grouped: GroupedItems | null) => void;
  setSelectedGroupBy: (groupBy: string | null) => void;
}

export function useExtendedGrouping({
  tasks,
  setGroupedTasks,
  setSelectedGroupBy,
}: UseExtendedGroupingProps) {
  const { t } = useTranslation();
  const { customOptions, getHandler, isCustomOption } = useCustomGrouping();

  const responsiblePartyLabel = t('responsible_party');
  const processGroupLabel = t('process_group');
  const responsiblePartyMeKey = 'spiff_synthetic_key_indicating_assigned_to_me';

  // Extended groupByOptions with custom options
  const groupByOptions = useMemo(
    () => [
      responsiblePartyLabel,
      processGroupLabel,
      ...customOptions.map(o => o.label),
    ],
    [responsiblePartyLabel, processGroupLabel, customOptions],
  );

  // Extended onGroupBySelect that handles custom options
  const onGroupBySelect = useCallback(
    (groupBy: string) => {
      if (!tasks) {
        return;
      }
      setSelectedGroupBy(groupBy);

      if (groupBy === processGroupLabel) {
        const grouped = tasks.reduce(
          (acc: GroupedItems, task: ProcessInstanceTask) => {
            const processGroupIdentifier = task.process_model_identifier
              .split('/')
              .slice(0, -1)
              .join('/');
            if (!acc[processGroupIdentifier]) {
              acc[processGroupIdentifier] = [];
            }
            acc[processGroupIdentifier].push(task);
            return acc;
          },
          {},
        );
        setGroupedTasks(grouped);
      } else if (groupBy === '') {
        setGroupedTasks(null);
        setSelectedGroupBy(null);
      } else if (isCustomOption(groupBy)) {
        // m8 Extension: Handle custom grouping options
        console.log(`[m8 Extension] Custom grouping selected: ${groupBy}`);
        const handler = getHandler(groupBy);
        if (handler) {
          const grouped = handler(tasks);
          setGroupedTasks(grouped);
        }
      } else if (groupBy === responsiblePartyLabel) {
        const grouped = tasks.reduce(
          (acc: GroupedItems, task: ProcessInstanceTask) => {
            const key =
              task.assigned_user_group_identifier || responsiblePartyMeKey;
            if (!acc[key]) {
              acc[key] = [];
            }
            acc[key].push(task);
            return acc;
          },
          {},
        );
        setGroupedTasks(grouped);
      }
    },
    [tasks, processGroupLabel, responsiblePartyLabel, isCustomOption, getHandler, setGroupedTasks, setSelectedGroupBy],
  );

  return {
    groupByOptions,
    onGroupBySelect,
    responsiblePartyMeKey,
  };
}

export default useExtendedGrouping;
