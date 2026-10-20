import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Check, Copy, MailPlus, RotateCw, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatLocale } from '@/i18n';
import { Alert } from '@/components/library/alert/Alert';
import { CheckboxField } from '@/components/library/checkbox-field/CheckboxField';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  createTenantInvitation,
  fetchTenantInvitations,
  invitationManagementErrorMessage,
  resendTenantInvitation,
  revokeTenantInvitation,
  type TenantInvitation,
} from '@/lib/invitationManagementApi';
import { TENANT_ROLES, type TenantRole } from '@/lib/tenantAdminApi';

const INVITATIONS_PAGE_SIZE = 100;
const VALIDITY_OPTIONS = [1, 7, 30] as const;
const EMAIL_PATTERN = /\S+@\S+\.\S+/;

type InvitationManagementSectionProps = {
  tenantId: string;
  inviteOpen: boolean;
  onInviteOpenChange: (open: boolean) => void;
  /**
   * Reports the live count of PENDING invitations after every successful
   * load — matches the tab's own "Pending invites" label, not the total
   * row count (the table itself still shows every status, accepted/revoked
   * included, for an audit trail). Feeds the count badge on
   * `TenantAdminPanel`'s tab trigger; omitted on error so a transient
   * failure doesn't zero out an already-shown count.
   */
  onCountChange?: (pendingCount: number) => void;
};

function statusTone(status: TenantInvitation['status']): NonNullable<PillProps['tone']> {
  if (status === 'PENDING') {
    return 'warning';
  }
  if (status === 'ACCEPTED') {
    return 'success';
  }
  if (status === 'EXPIRED') {
    return 'error';
  }
  return 'muted';
}

function formatExpiry(seconds: number): string {
  try {
    return new Date(seconds * 1000).toLocaleString(formatLocale());
  } catch {
    return String(seconds);
  }
}

export default function InvitationManagementSection({
  tenantId,
  inviteOpen,
  onInviteOpenChange,
  onCountChange,
}: InvitationManagementSectionProps) {
  const { t } = useTranslation();
  const [invitations, setInvitations] = useState<TenantInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const [email, setEmail] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<TenantRole[]>([]);
  const [validityDays, setValidityDays] = useState<(typeof VALIDITY_OPTIONS)[number]>(7);
  const [sending, setSending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTenantInvitations(tenantId, { limit: INVITATIONS_PAGE_SIZE })
      .then((payload) => {
        if (!cancelled) {
          setInvitations(payload.results);
          onCountChange?.(payload.results.filter((invitation) => invitation.status === 'PENDING').length);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(invitationManagementErrorMessage(err, t('tenantManagement.invitations.errors.load')));
          setInvitations([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // onCountChange intentionally excluded from deps — it's not this
    // effect's own trigger; TenantAdminPanel passes an inline callback, so
    // treating it as a dep would re-fetch on every parent render.
  }, [tenantId, reloadKey]);

  const canSubmit = useMemo(
    () => EMAIL_PATTERN.test(email.trim()) && selectedRoles.length > 0 && !sending,
    [email, selectedRoles, sending],
  );

  function resetInviteForm() {
    setEmail('');
    setSelectedRoles([]);
    setValidityDays(7);
    setInviteError(null);
    setDevLink(null);
    setLinkCopied(false);
    setSending(false);
  }

  function closeInvite() {
    if (sending) {
      return;
    }
    resetInviteForm();
    onInviteOpenChange(false);
  }

  function toggleRole(role: TenantRole) {
    setSelectedRoles((current) =>
      current.includes(role) ? current.filter((item) => item !== role) : [...current, role],
    );
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setSending(true);
    setInviteError(null);
    setDevLink(null);
    try {
      const payload = await createTenantInvitation(tenantId, {
        email: email.trim(),
        roles: selectedRoles,
        validity_days: validityDays,
      });
      setReloadKey((key) => key + 1);
      if (payload.invitation.invitation_link) {
        setDevLink(payload.invitation.invitation_link);
        setSending(false);
        return;
      }
      resetInviteForm();
      onInviteOpenChange(false);
    } catch (err: unknown) {
      setInviteError(invitationManagementErrorMessage(err, t('tenantManagement.invitations.errors.send')));
      setSending(false);
    }
  }

  async function handleCopyLink() {
    if (!devLink) {
      return;
    }
    const clipboard = navigator.clipboard;
    if (!clipboard?.writeText) {
      setInviteError(t('tenantManagement.invitations.errors.copyUnavailable'));
      return;
    }

    try {
      await clipboard.writeText(devLink);
      setInviteError(null);
      setLinkCopied(true);
    } catch (err: unknown) {
      setLinkCopied(false);
      setInviteError(
        invitationManagementErrorMessage(
          err,
          t('tenantManagement.invitations.errors.copyFailed'),
        ),
      );
    }
  }

  async function handleResend(invitation: TenantInvitation) {
    setMutatingId(invitation.id);
    setError(null);
    try {
      await resendTenantInvitation(tenantId, invitation.id);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(invitationManagementErrorMessage(err, t('tenantManagement.invitations.errors.resend')));
    } finally {
      setMutatingId(null);
    }
  }

  async function handleRevoke(invitation: TenantInvitation) {
    setMutatingId(invitation.id);
    setError(null);
    try {
      await revokeTenantInvitation(tenantId, invitation.id);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(invitationManagementErrorMessage(err, t('tenantManagement.invitations.errors.revoke')));
    } finally {
      setMutatingId(null);
    }
  }

  const columns: DataTableColumn<TenantInvitation>[] = [
    {
      key: 'email',
      header: t('tenantManagement.invitations.columnEmail'),
      width: 'minmax(160px,1.6fr)',
      render: (invitation) => invitation.email,
    },
    {
      key: 'roles',
      header: t('tenantManagement.invitations.columnRoles'),
      width: 'minmax(120px,1fr)',
      render: (invitation) => (
        <div className="flex flex-wrap gap-1">
          {invitation.roles.map((role) => (
            <Badge key={role} variant="outline">
              {role}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 'minmax(100px,120px)',
      render: (invitation) => (
        <Pill tone={statusTone(invitation.status)} dot={false}>
          {t(`tenantManagement.invitations.statusLabel.${invitation.status}`, { defaultValue: invitation.status })}
        </Pill>
      ),
    },
    {
      key: 'expires',
      header: t('tenantManagement.invitations.columnExpires'),
      width: 'minmax(140px,1fr)',
      render: (invitation) => (
        <span className="text-muted-foreground">
          {formatExpiry(invitation.expires_at_in_seconds)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">{t('common.actions')}</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(160px,1fr)',
      render: (invitation) => {
        const isPending = invitation.status === 'PENDING';
        const canResend = invitation.status === 'PENDING' || invitation.status === 'EXPIRED';
        const isMutating = mutatingId === invitation.id;
        return (
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!canResend || isMutating}
              onClick={() => void handleResend(invitation)}
              data-testid={`invitation-resend-${invitation.id}`}
            >
              <RotateCw className="size-3.5" aria-hidden />
              {t('tenantManagement.invitations.resend')}
            </Button>
            <Button
              type="button"
              variant="ghost-destructive"
              size="sm"
              disabled={!isPending || isMutating}
              onClick={() => void handleRevoke(invitation)}
              data-testid={`invitation-revoke-${invitation.id}`}
            >
              <Trash2 className="size-3.5" aria-hidden />
              {t('tenantManagement.invitations.revoke')}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <>
      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <Card variant="bordered" className="overflow-hidden" data-testid="pending-invitations-panel">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            {t('tenantManagement.invitations.loading')}
          </p>
        ) : invitations.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            {t('tenantManagement.invitations.empty')}
          </p>
        ) : (
          <DataTable columns={columns} rows={invitations} getRowKey={(invitation) => invitation.id} />
        )}
      </Card>

      <Modal
        open={inviteOpen}
        onOpenChange={(open) => {
          if (!open) {
            closeInvite();
          } else {
            onInviteOpenChange(true);
          }
        }}
        title={
          devLink
            ? t('tenantManagement.invitations.invite.createdTitle')
            : t('tenantManagement.invitations.invite.title')
        }
        footer={
          devLink ? (
            <Button type="button" variant="pill-dark" size="pill" onClick={closeInvite}>
              {t('tenantManagement.invitations.invite.done')}
            </Button>
          ) : (
            <>
              <Button type="button" variant="pill-cancel" size="pill" onClick={closeInvite}>
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                form="invite-user-form"
                variant="pill-dark"
                size="pill"
                disabled={!canSubmit}
                data-testid="invite-user-submit"
              >
                <MailPlus className="size-3.5" aria-hidden />
                {sending
                  ? t('tenantManagement.invitations.invite.sending')
                  : t('tenantManagement.invitations.invite.send')}
              </Button>
            </>
          )
        }
      >
        {devLink ? (
          <>
            <p className="text-[13.5px] text-muted-foreground">
              {t('tenantManagement.invitations.invite.devLinkHint')}
            </p>
            <div className="mt-4 flex items-center gap-2">
              <Input
                className="min-w-0 flex-1"
                value={devLink}
                readOnly
                aria-label={t('tenantManagement.invitations.invite.invitationUrl')}
                data-testid="invite-user-dev-link"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleCopyLink()}
                data-testid="invite-copy-link"
              >
                {linkCopied ? (
                  <>
                    <Check className="size-3.5" aria-hidden />
                    {t('tenantManagement.invitations.invite.copied')}
                  </>
                ) : (
                  <>
                    <Copy className="size-3.5" aria-hidden />
                    {t('tenantManagement.invitations.invite.copyUrl')}
                  </>
                )}
              </Button>
            </div>
            {inviteError ? (
              <Alert tone="error" className="mt-3">
                {inviteError}
              </Alert>
            ) : null}
          </>
        ) : (
          <form id="invite-user-form" onSubmit={(event) => void handleCreate(event)}>
            <p className="text-[13.5px] text-muted-foreground">
              {t('tenantManagement.invitations.invite.formHint')}
            </p>
            <label className="mt-4 block text-sm font-medium text-foreground">
              {t('tenantManagement.invitations.invite.emailAddress')}
              <Input
                className="mt-1.5"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="off"
                data-testid="invite-user-email-input"
                required
              />
            </label>
            <fieldset className="mt-4">
              <legend className="text-sm font-medium">
                {t('tenantManagement.invitations.invite.roles')}
              </legend>
              <div className="mt-2 flex flex-col gap-1">
                {TENANT_ROLES.map((role) => (
                  <CheckboxField
                    key={role}
                    label={role}
                    checked={selectedRoles.includes(role)}
                    onCheckedChange={() => toggleRole(role)}
                    data-testid={`invite-user-role-${role}`}
                  />
                ))}
              </div>
            </fieldset>
            <div className="mt-4">
              <label htmlFor="invite-user-validity" className="block text-sm font-medium text-foreground">
                {t('tenantManagement.invitations.invite.validity')}
              </label>
              <Select
                value={String(validityDays)}
                onValueChange={(value) =>
                  setValidityDays(Number(value) as (typeof VALIDITY_OPTIONS)[number])
                }
              >
                <SelectTrigger id="invite-user-validity" data-testid="invite-user-validity" className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VALIDITY_OPTIONS.map((days) => (
                    <SelectItem key={days} value={String(days)}>
                      {days === 7
                        ? t('tenantManagement.invitations.invite.validityDaysDefault', { count: days })
                        : t('tenantManagement.invitations.invite.validityDays', { count: days })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {inviteError ? (
              <Alert tone="error" className="mt-3">
                {inviteError}
              </Alert>
            ) : null}
          </form>
        )}
      </Modal>
    </>
  );
}
