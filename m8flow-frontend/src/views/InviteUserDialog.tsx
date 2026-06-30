import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import TenantService, {
  TENANT_MEMBER_ROLES,
  TenantMemberRole,
} from "../services/TenantService";

interface InviteUserDialogProps {
  open: boolean;
  tenantId: string | null;
  onClose: () => void;
  onInvited: () => void;
}

const ROLE_DESCRIPTION_FALLBACK: Record<TenantMemberRole, string> = {
  "tenant-admin": "Full access to tenant management and settings",
  editor: "Can create and edit processes",
  integrator: "Can manage integrations and connectors",
  reviewer: "Can review and approve processes",
  submitter: "Can submit process instances",
  viewer: "Can view processes and instances",
};

const VALIDITY_OPTIONS = [1, 7, 30];

function getErrorMessage(error: any): string {
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return "Failed to send invitation.";
}

export default function InviteUserDialog({
  open,
  tenantId,
  onClose,
  onInvited,
}: InviteUserDialogProps) {
  const { t } = useTranslation();
  const translate = (key: string, fallback: string) => {
    const translated = t(key);
    return translated === key ? fallback : translated;
  };

  const [email, setEmail] = useState("");
  const [selectedRoles, setSelectedRoles] = useState<TenantMemberRole[]>([]);
  const [validityDays, setValidityDays] = useState(7);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [devLink, setDevLink] = useState<string | null>(null);

  const roleLabel = (roleName: TenantMemberRole) => {
    const key = `tenant_role_${roleName.replace(/-/g, "_")}`;
    const translated = t(key);
    return translated === key ? roleName : translated;
  };

  const isValidEmail = useMemo(() => /\S+@\S+\.\S+/.test(email.trim()), [email]);
  const canSubmit = Boolean(tenantId) && isValidEmail && selectedRoles.length > 0 && !isSubmitting;

  const resetForm = () => {
    setEmail("");
    setSelectedRoles([]);
    setValidityDays(7);
    setErrorMessage("");
    setDevLink(null);
    setIsSubmitting(false);
  };

  const handleClose = () => {
    if (isSubmitting) {
      return;
    }
    resetForm();
    onClose();
  };

  const toggleRole = (roleName: TenantMemberRole) => {
    setSelectedRoles((current) =>
      current.includes(roleName)
        ? current.filter((role) => role !== roleName)
        : [...current, roleName],
    );
  };

  const handleSubmit = () => {
    if (!tenantId || !canSubmit) {
      return;
    }
    setIsSubmitting(true);
    setErrorMessage("");
    setDevLink(null);
    TenantService.createInvitation(tenantId, {
      email: email.trim(),
      roles: selectedRoles,
      validity_days: validityDays,
    })
      .then((invitation) => {
        setIsSubmitting(false);
        onInvited();
        if (invitation.invitation_link) {
          // Dev mode: SMTP not configured, surface the link so it can be tested.
          setDevLink(invitation.invitation_link);
        } else {
          resetForm();
          onClose();
        }
      })
      .catch((error) => {
        setIsSubmitting(false);
        setErrorMessage(getErrorMessage(error));
      });
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {translate("invite_user", "Invite User")}
        <IconButton onClick={handleClose} size="small" aria-label={translate("close", "Close")}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {devLink ? (
          <Stack spacing={2}>
            <Alert severity="success">
              {translate(
                "invitation_created_dev_mode",
                "Invitation created. Email is not configured, so share this single-use link with the user:",
              )}
            </Alert>
            <TextField
              value={devLink}
              fullWidth
              size="small"
              multiline
              InputProps={{
                readOnly: true,
                endAdornment: (
                  <IconButton
                    size="small"
                    aria-label={translate("copy", "Copy")}
                    onClick={() => navigator.clipboard?.writeText(devLink)}
                  >
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                ),
              }}
            />
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={handleClose} variant="contained">
                {translate("done", "Done")}
              </Button>
            </Box>
          </Stack>
        ) : (
          <Stack spacing={2}>
            {errorMessage && <Alert severity="error">{errorMessage}</Alert>}
            <Box>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                {translate("email_address", "Email Address")} *
              </Typography>
              <TextField
                fullWidth
                size="small"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={translate("enter_email_address", "Enter email address")}
                inputProps={{ "data-testid": "invite-user-email-input" }}
              />
              <Typography variant="caption" color="text.secondary">
                {translate("invitation_email_hint", "An invitation link will be sent to this email.")}
              </Typography>
            </Box>
            <Box>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                {translate("select_roles", "Select Roles")} *
              </Typography>
              <Stack>
                {TENANT_MEMBER_ROLES.map((roleName) => (
                  <FormControlLabel
                    key={roleName}
                    control={
                      <Checkbox
                        checked={selectedRoles.includes(roleName)}
                        onChange={() => toggleRole(roleName)}
                        data-testid={`invite-user-role-${roleName}`}
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2">{roleLabel(roleName)}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {translate(
                            `tenant_role_${roleName.replace(/-/g, "_")}_description`,
                            ROLE_DESCRIPTION_FALLBACK[roleName],
                          )}
                        </Typography>
                      </Box>
                    }
                    sx={{ alignItems: "flex-start", mb: 0.5 }}
                  />
                ))}
              </Stack>
            </Box>
            <FormControl fullWidth size="small">
              <InputLabel id="invitation-validity-label">
                {translate("invitation_validity", "Invitation Validity")}
              </InputLabel>
              <Select
                labelId="invitation-validity-label"
                label={translate("invitation_validity", "Invitation Validity")}
                value={validityDays}
                onChange={(event) => setValidityDays(Number(event.target.value))}
              >
                {VALIDITY_OPTIONS.map((days) => (
                  <MenuItem key={days} value={days}>
                    {days === 7
                      ? translate("validity_seven_days_default", "7 days (Default)")
                      : `${days} ${translate("days", "days")}`}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Alert severity="info" icon={false}>
              {translate(
                "invitation_link_notice",
                "The invitation link will expire after the selected duration and can only be used once.",
              )}
            </Alert>
          </Stack>
        )}
      </DialogContent>
      {!devLink && (
        <DialogActions>
          <Button onClick={handleClose} disabled={isSubmitting}>
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!canSubmit}
            data-testid="invite-user-submit"
          >
            {translate("send_invitation", "Send Invitation")}
          </Button>
        </DialogActions>
      )}
    </Dialog>
  );
}
