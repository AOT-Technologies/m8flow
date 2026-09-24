import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { login } from '@/lib/auth';
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
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
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

  // Card-on-tinted-surface shell, so this pre-login page reads as the same
  // product as the Keycloak sign-in card it hands off to, rather than bare
  // text on a white page.
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 px-6 py-12 text-foreground">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center text-[26px] font-bold tracking-tight">
          m8<span className="text-primary">flow</span>
        </div>
        <Card variant="bordered" className="px-7 py-7">
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Complete your registration
          </h1>
          {/* Only the password form needs the instruction — after activation
              (or on a dead link) it would contradict what's on screen. */}
          {validation && !validationError && !isAccepted ? (
            <p className="mt-1.5 text-sm text-muted-foreground">
              Set a password to activate your account.
            </p>
          ) : null}
          <div className="mt-6">{renderBody()}</div>
        </Card>
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
        <div className="space-y-5">
          <Alert tone="success">
            Your account has been activated. You can now sign in with your email and password.
          </Alert>
          {/* `href="/"` silently walked into the app whenever the browser
              still held another user's session — the point here is to sign in
              as the account just activated, so force Keycloak's prompt. */}
          <Button
            type="button"
            size="lg"
            className="w-full"
            onClick={() => login({ promptLogin: true, redirectUrl: `${window.location.origin}/` })}
            data-testid="accept-invitation-go-login"
          >
            Go to login
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
        {/* Invitation facts grouped into one read-only panel so the eye
            separates "what you were invited to" from "what you must fill in". */}
        <div className="space-y-3 rounded-xl border border-border bg-muted/40 px-4 py-3.5">
          <div>
            <p className="text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">
              You have been invited to join
            </p>
            <p className="mt-0.5 text-sm font-semibold">{validation.tenant_name}</p>
          </div>
          <div>
            <p className="text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">
              Email
            </p>
            <p className="mt-0.5 text-sm break-all">{validation.email}</p>
          </div>
          <div>
            <p className="text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">
              Roles
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {validation.roles.map((role) => (
                <Pill key={role} tone="muted" dot={false}>
                  {role}
                </Pill>
              ))}
            </div>
          </div>
        </div>
        {submitError ? <Alert tone="error">{submitError}</Alert> : null}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Password</span>
          <div className="relative">
            <Input
              className="pr-10"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={password.length > 0 && !passwordLongEnough}
              data-testid="accept-invitation-password"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="absolute top-1/2 right-1 -translate-y-1/2"
              onClick={() => setShowPassword((visible) => !visible)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              data-testid="accept-invitation-password-toggle"
            >
              {showPassword ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
            </Button>
          </div>
          <span className="text-xs text-muted-foreground">
            Use at least {MIN_PASSWORD_LENGTH} characters.
          </span>
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Confirm password</span>
          <div className="relative">
            <Input
              className="pr-10"
              type={showConfirmPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              aria-invalid={confirmPassword.length > 0 && !passwordsMatch}
              data-testid="accept-invitation-confirm-password"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="absolute top-1/2 right-1 -translate-y-1/2"
              onClick={() => setShowConfirmPassword((visible) => !visible)}
              aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
              aria-pressed={showConfirmPassword}
              data-testid="accept-invitation-confirm-password-toggle"
            >
              {showConfirmPassword ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
            </Button>
          </div>
          {confirmPassword.length > 0 && !passwordsMatch ? (
            <span className="text-xs text-destructive">Passwords do not match.</span>
          ) : null}
        </label>
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={!canSubmit}
          data-testid="accept-invitation-submit"
        >
          {isSubmitting ? 'Processing…' : 'Set password and activate'}
        </Button>
      </form>
    );
  }
}
