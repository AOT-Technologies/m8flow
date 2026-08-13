/**
 * Process-model reference list dialog (extracted from the diagram editor shell).
 */
import { Modal, UnorderedList, Link } from '@carbon/react';
import { useTranslation } from 'react-i18next';
import { modifyProcessIdentifierForPathParam } from '../helpers';
import type { ProcessReference } from '../interfaces';

type Props = {
  open: boolean;
  onClose: () => void;
  callers: ProcessReference[] | undefined;
};

export default function ReferencesModal({ open, onClose, callers }: Props) {
  const { t } = useTranslation();
  if (!callers) return null;

  return (
    <Modal
      open={open}
      passiveModal
      modalHeading={t('diagram_process_model_references')}
      onRequestClose={onClose}
      data-testid="references-modal"
    >
      <UnorderedList>
        {callers.map((item) => {
          const href = `/process-models/${modifyProcessIdentifierForPathParam(
            item.relative_location,
          )}`;
          return (
            <li key={item.relative_location}>
              <Link
                size="lg"
                href={href}
                data-testid={`reference-link-${item.identifier}`}
              >
                {item.display_name}
              </Link>{' '}
              ({item.relative_location})
            </li>
          );
        })}
      </UnorderedList>
    </Modal>
  );
}
