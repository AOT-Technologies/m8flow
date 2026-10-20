import { CircleSlash, Copy, Files, PauseCircle, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ActionMenu, type ActionMenuItem } from '@/components/library/action-menu/ActionMenu';
import type { ProcessModelStatus } from '@/lib/api';

export type HeaderActionsMenuProps = {
  onEditIdentity?: () => void;
  onCopy?: () => void;
  onSaveAsTemplate?: () => void;
  /** Current lifecycle status — decides which transitions are offered. */
  status?: ProcessModelStatus;
  /** Moves the model through the publish lifecycle. Absent for users who
   * can't manage processes, so no action is shown that would 403. */
  onChangeStatus?: (status: ProcessModelStatus) => void;
};

/** Overflow menu for secondary process-model actions, built on
 * `library/action-menu`'s `ActionMenu` (component-adoption map, ticket 07 —
 * this file used to hand-roll its own open/outside-click/Escape state, the
 * 2nd of 3 duplicate implementations found by ticket 21's audit). Save as
 * template is enabled only when the caller can POST templates (catalog
 * manager, not super-admin). */
export function HeaderActionsMenu({
  onEditIdentity,
  onCopy,
  onSaveAsTemplate,
  status,
  onChangeStatus,
}: HeaderActionsMenuProps) {
  const { t } = useTranslation();
  const items: ActionMenuItem[] = [
    ...(onEditIdentity
      ? [
          {
            label: t('processModelDetail.actions.editIdentity'),
            icon: <Pencil className="size-3.5" strokeWidth={2} />,
            onSelect: onEditIdentity,
          },
        ]
      : []),
    // Publish / Resume are the page's primary button, not menu items. Only
    // the transitions the backend accepts from here are offered (draft gets
    // no Pause: draft -> paused is a 400).
    ...(onChangeStatus && status === 'published'
      ? [
          {
            label: t('processModelDetail.actions.pause'),
            icon: <PauseCircle className="size-3.5" strokeWidth={2} />,
            onSelect: () => onChangeStatus('paused'),
          },
        ]
      : []),
    ...(onChangeStatus && status !== 'draft'
      ? [
          {
            label: t('processModelDetail.actions.unpublish'),
            icon: <CircleSlash className="size-3.5" strokeWidth={2} />,
            onSelect: () => onChangeStatus('draft'),
          },
        ]
      : []),
    ...(onCopy
      ? [{
          label: t('processModelDetail.actions.copy'),
          icon: <Copy className="size-3.5" strokeWidth={2} />,
          onSelect: onCopy,
        }]
      : []),
    ...(onSaveAsTemplate
      ? [{
          label: t('processModelDetail.actions.saveAsTemplate'),
          icon: <Files className="size-3.5" strokeWidth={2} />,
          onSelect: onSaveAsTemplate,
        }]
      : []),
  ];

  return <ActionMenu size="header" contentClassName="w-52" items={items} />;
}
