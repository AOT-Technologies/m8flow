import { CircleSlash, Copy, Files, PauseCircle, Pencil } from 'lucide-react';

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
  const items: ActionMenuItem[] = [
    ...(onEditIdentity
      ? [
          {
            label: 'Edit identity',
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
            label: 'Pause',
            icon: <PauseCircle className="size-3.5" strokeWidth={2} />,
            onSelect: () => onChangeStatus('paused'),
          },
        ]
      : []),
    ...(onChangeStatus && status !== 'draft'
      ? [
          {
            label: 'Unpublish',
            icon: <CircleSlash className="size-3.5" strokeWidth={2} />,
            onSelect: () => onChangeStatus('draft'),
          },
        ]
      : []),
    {
      label: 'Copy',
      icon: <Copy className="size-3.5" strokeWidth={2} />,
      disabled: !onCopy,
      onSelect: () => onCopy?.(),
    },
    {
      label: 'Save as template',
      icon: <Files className="size-3.5" strokeWidth={2} />,
      disabled: !onSaveAsTemplate,
      onSelect: () => onSaveAsTemplate?.(),
    },
  ];

  return <ActionMenu size="header" contentClassName="w-52" items={items} />;
}
