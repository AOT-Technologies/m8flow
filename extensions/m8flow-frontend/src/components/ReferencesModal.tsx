import React from 'react';
import { Modal, UnorderedList, Link } from '@carbon/react';
import { ProcessReference } from '@spiffworkflow-frontend/interfaces';
import { modifyProcessIdentifierForPathParam } from '@spiffworkflow-frontend/helpers';
import { useTranslation } from 'react-i18next';

export type ReferencesModalProps = {
  open: boolean;
  onClose: () => void;
  callers: ProcessReference[] | undefined;
};

export default function ReferencesModal({
  open,
  onClose,
  callers,
}: ReferencesModalProps) {
  const { t } = useTranslation();

  if (!callers) {
    return null;
  }

  return (
    <Modal
      open={open}
      modalHeading={t('diagram_process_model_references')}
      onRequestClose={onClose}
      passiveModal
    >
      <UnorderedList>
        {callers.map((ref: ProcessReference) => (
          <li key={`list-${ref.relative_location}`}>
            <Link
              size="lg"
              href={`/process-models/${modifyProcessIdentifierForPathParam(
                ref.relative_location,
              )}`}
            >
              {`${ref.display_name}`}
            </Link>{' '}
            ({ref.relative_location})
          </li>
        ))}
      </UnorderedList>
    </Modal>
  );
}
