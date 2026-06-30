import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import TenantService, {
  InvitationValidation,
  TenantMemberRole,
} from "../services/TenantService";

const MIN_PASSWORD_LENGTH = 8;

function getErrorMessage(error: any, fallback: string): string {
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  return fallback;
}

function getTokenFromUrl(): string {
  if (typeof globalThis === "undefined" || !globalThis.location) {
    return "";
  }
  return new URLSearchParams(globalThis.location.search).get("token") ?? "";
}

export default function AcceptInvitationPage() {
  const { t } = useTranslation();
  const translate = (key: string, fallback: string) => {
    const translated = t(key);
    return translated === key ? fallback : translated;
  };

  const token = useMemo(getTokenFromUrl, []);
  const [isValidating, setIsValidating] = useState(true);
  const [validation, setValidation] = useState<InvitationValidation | null>(null);
  const [validationError, setValidationError] = useState("");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [isAccepted, setIsAccepted] = useState(false);

  const roleLabel = (roleName: TenantMemberRole) => {
    const key = `tenant_role_${roleName.replace(/-/g, "_")}`;
    const translated = t(key);
    return translated === key ? roleName : translated;
  };

  useEffect(() => {
    if (!token) {
      setIsValidating(false);
      setValidationError(
        translate("invitation_missing_token", "This invitation link is missing its token."),
      );
      return;
    }
    TenantService.validateInvitation(token)
      .then((result) => {
        setValidation(result);
        setIsValidating(false);
      })
      .catch((error) => {
        setValidationError(
          getErrorMessage(error, translate("invitation_invalid", "This invitation link is invalid or has expired.")),
        );
        setIsValidating(false);
      });
  }, [token]);

  const passwordsMatch = password.length > 0 && password === confirmPassword;
  const passwordLongEnough = password.length >= MIN_PASSWORD_LENGTH;
  const canSubmit = Boolean(validation) && passwordLongEnough && passwordsMatch && !isSubmitting;

  const handleSubmit = () => {
    if (!canSubmit) {
      return;
    }
    setIsSubmitting(true);
    setSubmitError("");
    TenantService.acceptInvitation(token, password)
      .then(() => {
        setIsSubmitting(false);
        setIsAccepted(true);
      })
      .catch((error) => {
        setIsSubmitting(false);
        setSubmitError(
          getErrorMessage(error, translate("invitation_accept_failed", "Failed to activate your account.")),
        );
      });
  };

  const renderBody = () => {
    if (isValidating) {
      return (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      );
    }

    if (isAccepted) {
      return (
        <Stack spacing={3}>
          <Alert severity="success">
            {translate(
              "invitation_account_activated",
              "Your account has been activated. You can now sign in with your email and password.",
            )}
          </Alert>
          <Button variant="contained" href="/login" data-testid="accept-invitation-go-login">
            {translate("go_to_login", "Go to login")}
          </Button>
        </Stack>
      );
    }

    if (validationError || !validation) {
      return (
        <Alert severity="error" data-testid="accept-invitation-error">
          {validationError || translate("invitation_invalid", "This invitation link is invalid or has expired.")}
        </Alert>
      );
    }

    return (
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="body2" color="text.secondary">
            {translate("invited_to_join", "You have been invited to join")}
          </Typography>
          <Typography variant="h6">{validation.tenant_name}</Typography>
        </Box>
        <Box>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {translate("email", "Email")}
          </Typography>
          <Typography variant="body1">{validation.email}</Typography>
        </Box>
        <Box>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {translate("roles", "Roles")}
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {validation.roles.map((role) => (
              <Chip key={role} label={roleLabel(role)} size="small" />
            ))}
          </Stack>
        </Box>
        {submitError && <Alert severity="error">{submitError}</Alert>}
        <TextField
          label={translate("password", "Password")}
          type="password"
          fullWidth
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          helperText={translate(
            "password_min_length_hint",
            `Use at least ${MIN_PASSWORD_LENGTH} characters.`,
          )}
          error={password.length > 0 && !passwordLongEnough}
          inputProps={{ "data-testid": "accept-invitation-password" }}
        />
        <TextField
          label={translate("confirm_password", "Confirm Password")}
          type="password"
          fullWidth
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          error={confirmPassword.length > 0 && !passwordsMatch}
          helperText={
            confirmPassword.length > 0 && !passwordsMatch
              ? translate("passwords_do_not_match", "Passwords do not match.")
              : " "
          }
          inputProps={{ "data-testid": "accept-invitation-confirm-password" }}
        />
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!canSubmit}
          data-testid="accept-invitation-submit"
        >
          {isSubmitting
            ? translate("processing", "Processing...")
            : translate("set_password_activate", "Set Password & Activate")}
        </Button>
      </Stack>
    );
  };

  return (
    <Container maxWidth="sm" sx={{ py: 6 }}>
      <Paper sx={{ p: 4 }}>
        <Typography variant="h5" fontWeight={600} gutterBottom>
          {translate("complete_registration", "Complete your registration")}
        </Typography>
        <Box sx={{ mt: 2 }}>{renderBody()}</Box>
      </Paper>
    </Container>
  );
}
