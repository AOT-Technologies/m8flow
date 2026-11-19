// SPDX-License-Identifier: Apache-2.0

import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { startProcessInstance, type CollaborationParticipant, type ProcessStartOptions } from '@/lib/api';

type PickerRequest = {
  participants: CollaborationParticipant[];
  resolve: (options: ProcessStartOptions | null) => void;
};

export function useProcessStart() {
  const [request, setRequest] = useState<PickerRequest | null>(null);

  async function start(
    modifiedId: string,
    tenantId: string | null | undefined,
    participants: CollaborationParticipant[] | null | undefined,
  ) {
    if (!participants) return startProcessInstance(modifiedId, tenantId);
    const options = await new Promise<ProcessStartOptions | null>((resolve) => {
      setRequest({ participants, resolve });
    });
    return options ? startProcessInstance(modifiedId, tenantId, options) : null;
  }

  const picker = request && (
    <ParticipantPicker
      participants={request.participants}
      onSelect={(options) => {
        setRequest(null);
        request.resolve(options);
      }}
    />
  );
  return { start, picker };
}

function ParticipantPicker({
  participants,
  onSelect,
}: {
  participants: CollaborationParticipant[];
  onSelect: (options: ProcessStartOptions | null) => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const [processId, setProcessId] = useState('');
  const [key, setKey] = useState('');
  const canStart = participants.some((participant) => participant.id === processId && participant.startable);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canStart || (key.length > 0 && !key.trim())) return;
    onSelect({
      bpmn_process_id: processId,
      ...(key ? { collaboration_correlation_key: key } : {}),
    });
  }

  return (
    <Modal
      open
      title={t('common.collaborationStart.title')}
      onOpenChange={(open) => { if (!open) onSelect(null); }}
      footer={
        <>
          <Button type="button" variant="outline" onClick={() => onSelect(null)}>{t('common.cancel')}</Button>
          <Button type="submit" form={formId} disabled={!canStart || (key.length > 0 && !key.trim())}>
            {t('common.collaborationStart.start')}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} className="grid gap-4">
        <label className="grid gap-1.5">
          {t('common.collaborationStart.participant')}
          <select
            className="h-9 rounded-md border border-input bg-background px-3"
            value={processId}
            onChange={(event) => setProcessId(event.target.value)}
            required
          >
            <option value="">{t('common.select')}</option>
            {participants.map((participant) => (
              <option key={participant.id} value={participant.id} disabled={!participant.startable}>
                {participant.startable
                  ? participant.name
                  : t('common.collaborationStart.eventStart', { name: participant.name })}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5">
          {t('common.collaborationStart.correlationKey')}
          <Input value={key} maxLength={255} onChange={(event) => setKey(event.target.value)} />
          <span className="text-xs text-muted-foreground">{t('common.collaborationStart.keyHint')}</span>
        </label>
      </form>
    </Modal>
  );
}
