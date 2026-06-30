import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  CircularProgress,
  Collapse,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SendIcon from "@mui/icons-material/Send";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import TenantService, {
  TenantInvitation,
  TenantInvitationStatus,
  TenantMemberRole,
} from "../services/TenantService";

interface PendingInvitationsPanelProps {
  tenantId: string | null;
  refreshKey: number;
}

const STATUS_COLOR: Record<TenantInvitationStatus, "warning" | "success" | "default" | "error"> = {
  PENDING: "warning",
  ACCEPTED: "success",
  REVOKED: "default",
  EXPIRED: "error",
};

function getErrorMessage(error: any): string {
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return "Something went wrong.";
}

export default function PendingInvitationsPanel({
  tenantId,
  refreshKey,
}: PendingInvitationsPanelProps) {
  const { t } = useTranslation();
  const translate = (key: string, fallback: string) => {
    const translated = t(key);
    return translated === key ? fallback : translated;
  };

  const [isExpanded, setIsExpanded] = useState(true);
  const [invitations, setInvitations] = useState<TenantInvitation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const roleLabel = (roleName: TenantMemberRole) => {
    const key = `tenant_role_${roleName.replace(/-/g, "_")}`;
    const translated = t(key);
    return translated === key ? roleName : translated;
  };

  const loadInvitations = useCallback(() => {
    if (!tenantId) {
      setInvitations([]);
      return;
    }
    setIsLoading(true);
    setErrorMessage("");
    TenantService.listInvitations(tenantId, { limit: 100 })
      .then((page) => {
        setInvitations(page.results);
        setIsLoading(false);
      })
      .catch((error) => {
        setErrorMessage(getErrorMessage(error));
        setIsLoading(false);
      });
  }, [tenantId]);

  useEffect(() => {
    loadInvitations();
  }, [loadInvitations, refreshKey]);

  const handleResend = (invitation: TenantInvitation) => {
    if (!tenantId) {
      return;
    }
    setMutatingId(invitation.id);
    TenantService.resendInvitation(tenantId, invitation.id)
      .then(() => {
        setMutatingId(null);
        loadInvitations();
      })
      .catch((error) => {
        setMutatingId(null);
        setErrorMessage(getErrorMessage(error));
      });
  };

  const handleRevoke = (invitation: TenantInvitation) => {
    if (!tenantId) {
      return;
    }
    setMutatingId(invitation.id);
    TenantService.revokeInvitation(tenantId, invitation.id)
      .then(() => {
        setMutatingId(null);
        loadInvitations();
      })
      .catch((error) => {
        setMutatingId(null);
        setErrorMessage(getErrorMessage(error));
      });
  };

  const formatExpiry = (seconds: number) => {
    try {
      return new Date(seconds * 1000).toLocaleString();
    } catch {
      return `${seconds}`;
    }
  };

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        overflow: "hidden",
      }}
      data-testid="pending-invitations-panel"
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2,
          py: 1.5,
          bgcolor: "action.hover",
        }}
      >
        <ButtonBase
          onClick={() => setIsExpanded((value) => !value)}
          aria-expanded={isExpanded}
          sx={{ flex: 1, justifyContent: "flex-start" }}
        >
          <Typography variant="subtitle1" fontWeight={600}>
            {translate("invitations", "Invitations")}
          </Typography>
        </ButtonBase>
        <IconButton onClick={() => setIsExpanded((value) => !value)} size="small">
          {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        </IconButton>
      </Box>
      <Collapse in={isExpanded} unmountOnExit>
        <Box sx={{ p: 2 }}>
          {errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage}
            </Alert>
          )}
          {isLoading ? (
            <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
              <CircularProgress />
            </Box>
          ) : invitations.length === 0 ? (
            <Box sx={{ py: 3, textAlign: "center" }}>
              <Typography color="text.secondary">
                {translate("no_invitations_found", "No invitations yet.")}
              </Typography>
            </Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{translate("email", "Email")}</TableCell>
                    <TableCell>{translate("roles", "Roles")}</TableCell>
                    <TableCell>{translate("status", "Status")}</TableCell>
                    <TableCell>{translate("expires", "Expires")}</TableCell>
                    <TableCell align="right">{translate("action", "Action")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {invitations.map((invitation) => {
                    const isPending = invitation.status === "PENDING";
                    const isMutating = mutatingId === invitation.id;
                    return (
                      <TableRow key={invitation.id}>
                        <TableCell>{invitation.email}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                            {invitation.roles.map((role) => (
                              <Chip key={role} label={roleLabel(role)} size="small" />
                            ))}
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={invitation.status}
                            size="small"
                            color={STATUS_COLOR[invitation.status]}
                          />
                        </TableCell>
                        <TableCell>{formatExpiry(invitation.expires_at_in_seconds)}</TableCell>
                        <TableCell align="right">
                          <Tooltip title={translate("resend_invitation", "Resend invitation")}>
                            <span>
                              <IconButton
                                size="small"
                                disabled={invitation.status === "ACCEPTED" || isMutating}
                                onClick={() => handleResend(invitation)}
                                data-testid={`invitation-resend-${invitation.id}`}
                              >
                                <SendIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title={translate("revoke_invitation", "Revoke invitation")}>
                            <span>
                              <IconButton
                                size="small"
                                color="error"
                                disabled={!isPending || isMutating}
                                onClick={() => handleRevoke(invitation)}
                                data-testid={`invitation-revoke-${invitation.id}`}
                              >
                                <DeleteOutlineIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
            <Button size="small" onClick={loadInvitations} disabled={isLoading}>
              {translate("refresh", "Refresh")}
            </Button>
          </Box>
        </Box>
      </Collapse>
    </Box>
  );
}
