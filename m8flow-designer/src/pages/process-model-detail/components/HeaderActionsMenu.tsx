import { Copy, Files, Pencil } from 'lucide-react';

import { ActionMenu, type ActionMenuItem } from '@/components/library/action-menu/ActionMenu';

export type HeaderActionsMenuProps = {
  onEditIdentity?: () => void;
  onCopy?: () => void;
  onSaveAsTemplate?: () => void;
};

/** Overflow menu for secondary process-model actions, built on
 * `library/action-menu`'s `ActionMenu` (component-adoption map, ticket 07 —
 * this file used to hand-roll its own open/outside-click/Escape state, the
 * 2nd of 3 duplicate implementations found by ticket 21's audit). Save as
 * template is enabled only when the caller can POST templates (catalog
 * manager, not super-admin). */
export function HeaderActionsMenu({ onEditIdentity, onCopy, onSaveAsTemplate }: HeaderActionsMenuProps) {
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
