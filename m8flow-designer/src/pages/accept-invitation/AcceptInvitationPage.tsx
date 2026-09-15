import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  acceptInvitation,
  invitationErrorMessage,
  validateInvitation,
  type InvitationValidation,
} from '@/lib/invitationsApi';

const MIN_PASSWORD_LENGTH = 8;

const MISSING_TOKEN_MESSAGE = 'This invitation link is missing its token.';
const INVALID_TOKEN_MESSAGE = 'This invitation link is invalid or has expired.';
const ACCEPT_FAILED_MESSAGE = 'Failed to activate your account.';

export default function AcceptInvitationPage() {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get('token')?.trim() ?? '', [searchParams]);

  const [isValidating, setIsValidating] = useState(true);
  const [validation, setValidation] = useState<InvitationValidation | null>(null);
  const [validationError, setValidationError] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [isAccepted, setIsAccepted] = useState(false);

  useEffect(() => {
    if (!token) {
      setIsValidating(false);
      setValidationError(MISSING_TOKEN_MESSAGE);
      return;
    }

    let ignore = false;
    setIsValidating(true);
    validateInvitation(token)
      .then((result) => {
        if (!ignore) {
          setValidation(result);
          setValidationError('');
          setIsValidating(false);
        }
      })
      .catch((error: unknown) => {
        if (!ignore) {
          setValidation(null);
          setValidationError(invitationErrorMessage(error, INVALID_TOKEN_MESSAGE));
          setIsValidating(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [token]);

  const passwordsMatch = password.length > 0 && password === confirmPassword;
  const passwordLongEnough = password.length >= MIN_PASSWORD_LENGTH;
  const canSubmit = Boolean(validation) && passwordLongEnough && passwordsMatch && !isSubmitting;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setIsSubmitting(true);
    setSubmitError('');
    acceptInvitation(token, password)
      .then(() => {
        setIsSubmitting(false);
        setIsAccepted(true);
      })
      .catch((error: unknown) => {
        setIsSubmitting(false);
        setSubmitError(invitationErrorMessage(error, ACCEPT_FAILED_MESSAGE));
      });
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12 text-foreground">
      <div className="w-full max-w-md space-y-6">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Complete your registration
        </h1>
        {renderBody()}
      </div>
    </main>
  );

  function renderBody() {
    if (isValidating) {
      return (
        <p className="text-sm text-muted-foreground" data-testid="accept-invitation-loading">
          Checking invitation…
        </p>
      );
    }

    if (isAccepted) {
      return (
        <div className="space-y-4">
          <Alert tone="success">
            Your account has been activated. You can now sign in with your email and password.
          </Alert>
          <Button asChild>
            <a href="/" data-testid="accept-invitation-go-login">
              Go to login
            </a>
          </Button>
        </div>
      );
    }

    if (validationError || !validation) {
      return (
        <Alert tone="error" data-testid="accept-invitation-error">
          {validationError || INVALID_TOKEN_MESSAGE}
        </Alert>
      );
    }

    return (
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">You have been invited to join</p>
          <p className="text-lg font-semibold">{validation.tenant_name}</p>
        </div>
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">Email</p>
          <p>{validation.email}</p>
        </div>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Roles</p>
          <div className="flex flex-wrap gap-1.5">
            {validation.roles.map((role) => (
              <Pill key={role} tone="muted" dot={false}>
                {role}
              </Pill>
            ))}
          </div>
        </div>
        {submitError ? <Alert tone="error">{submitError}</Alert> : null}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Password</span>
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={password.length > 0 && !passwordLongEnough}
            data-testid="accept-invitation-password"
          />
          <span className="text-xs text-muted-foreground">
            Use at least {MIN_PASSWORD_LENGTH} characters.
          </span>
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Confirm password</span>
          <Input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            aria-invalid={confirmPassword.length > 0 && !passwordsMatch}
            data-testid="accept-invitation-confirm-password"
          />
          {confirmPassword.length > 0 && !passwordsMatch ? (
            <span className="text-xs text-destructive">Passwords do not match.</span>
          ) : null}
        </label>
        <Button type="submit" disabled={!canSubmit} data-testid="accept-invitation-submit">
          {isSubmitting ? 'Processing…' : 'Set password and activate'}
        </Button>
      </form>
    );
  }
}
