import { FormEvent, useEffect, useMemo, useState } from 'react';
import { MailPlus, RotateCw, Trash2 } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { CheckboxField } from '@/components/library/checkbox-field/CheckboxField';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
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
    return new Date(seconds * 1000).toLocaleString();
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
          setError(invitationManagementErrorMessage(err, 'Failed to load invitations'));
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
      setInviteError(invitationManagementErrorMessage(err, 'Failed to send invitation'));
      setSending(false);
    }
  }

  async function handleResend(invitation: TenantInvitation) {
    setMutatingId(invitation.id);
    setError(null);
    try {
      await resendTenantInvitation(tenantId, invitation.id);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(invitationManagementErrorMessage(err, 'Failed to resend invitation'));
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
      setError(invitationManagementErrorMessage(err, 'Failed to revoke invitation'));
    } finally {
      setMutatingId(null);
    }
  }

  const columns: DataTableColumn<TenantInvitation>[] = [
    {
      key: 'email',
      header: 'Email',
      width: 'minmax(160px,1.6fr)',
      render: (invitation) => invitation.email,
    },
    {
      key: 'roles',
      header: 'Roles',
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
      header: 'Status',
      width: 'minmax(100px,120px)',
      render: (invitation) => (
        <Pill tone={statusTone(invitation.status)} dot={false}>
          {invitation.status}
        </Pill>
      ),
    },
    {
      key: 'expires',
      header: 'Expires',
      width: 'minmax(140px,1fr)',
      render: (invitation) => (
        <span className="text-muted-foreground">
          {formatExpiry(invitation.expires_at_in_seconds)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(160px,1fr)',
      render: (invitation) => {
        const isPending = invitation.status === 'PENDING';
        const canResend = invitation.status === 'PENDING' || invitation.status === 'EXPIRED';
        const isMutating = mutatingId === invitation.id;
        return (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!canResend || isMutating}
              onClick={() => void handleResend(invitation)}
              data-testid={`invitation-resend-${invitation.id}`}
            >
              <RotateCw className="size-3.5" aria-hidden />
              Resend
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!isPending || isMutating}
              onClick={() => void handleRevoke(invitation)}
              data-testid={`invitation-revoke-${invitation.id}`}
            >
              <Trash2 className="size-3.5" aria-hidden />
              Revoke
            </Button>
          </>
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
          <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading invitations…</p>
        ) : invitations.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">No invitations yet.</p>
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
        title={devLink ? 'Invitation created' : 'Invite User'}
        footer={
          devLink ? (
            <Button type="button" variant="pill-dark" size="pill" onClick={closeInvite}>
              Done
            </Button>
          ) : (
            <>
              <Button type="button" variant="pill-cancel" size="pill" onClick={closeInvite}>
                Cancel
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
                {sending ? 'Sending…' : 'Send Invitation'}
              </Button>
            </>
          )
        }
      >
        {devLink ? (
          <>
            <p className="text-[13.5px] text-muted-foreground">
              Email is not configured, so share this single-use link. It uses the Accept
              invitation path, not this admin panel.
            </p>
            <Input className="mt-4" value={devLink} readOnly />
          </>
        ) : (
          <form id="invite-user-form" onSubmit={(event) => void handleCreate(event)}>
            <p className="text-[13.5px] text-muted-foreground">
              Email a new person to join this tenant. If they already have an account, use Add
              Member instead.
            </p>
            <label className="mt-4 block text-sm font-medium text-foreground">
              Email address
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
              <legend className="text-sm font-medium">Roles</legend>
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
            <label className="mt-4 block text-sm font-medium text-foreground">
              Invitation validity
              <select
                className="mt-1.5 w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
                value={validityDays}
                onChange={(event) =>
                  setValidityDays(Number(event.target.value) as (typeof VALIDITY_OPTIONS)[number])
                }
                data-testid="invite-user-validity"
              >
                {VALIDITY_OPTIONS.map((days) => (
                  <option key={days} value={days}>
                    {days === 7 ? '7 days (Default)' : `${days} days`}
                  </option>
                ))}
              </select>
            </label>
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
