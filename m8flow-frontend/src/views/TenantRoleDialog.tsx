import {
  Alert,
  Box,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import TenantService, { Tenant, TenantMember, TenantMemberRole } from "../services/TenantService";

interface TenantRoleDialogProps {
  open: boolean;
  tenant: Tenant | null;
  onClose: () => void;
}

const TENANT_ROLE_NAMES: TenantMemberRole[] = [
  "tenant-admin",
  "editor",
  "integrator",
  "reviewer",
  "viewer",
];

function getErrorMessage(error: any): string {
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return "";
}

export default function TenantRoleDialog({
  open,
  tenant,
  onClose,
}: TenantRoleDialogProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [pendingRoleKey, setPendingRoleKey] = useState<string | null>(null);

  const translate = (
    key: string,
    fallback: string,
    options?: Record<string, unknown>,
  ) => {
    const translated = t(key, options);
    return translated === key ? fallback : translated;
  };

  const loadMembers = async () => {
    if (!tenant) {
      return;
    }
    setLoading(true);
    setErrorMessage("");
    try {
      const nextMembers = await TenantService.getTenantMembers(tenant.id);
      setMembers(nextMembers);
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error) ||
          translate(
            "failed_to_load_organization_members",
            "Failed to load organization members.",
          ),
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !tenant) {
      setSearchQuery("");
      setMembers([]);
      setErrorMessage("");
      setPendingRoleKey(null);
      return;
    }
    loadMembers();
  }, [open, tenant]);

  const filteredMembers = members.filter((member) => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return true;
    }
    return [
      member.username,
      member.display_name ?? "",
      member.email ?? "",
    ].some((value) => value.toLowerCase().includes(normalizedQuery));
  });

  const roleLabel = (roleName: TenantMemberRole) =>
    translate(`tenant_role_${roleName.replace(/-/g, "_")}`, roleName);

  const handleRoleToggle = async (
    member: TenantMember,
    roleName: TenantMemberRole,
    checked: boolean,
  ) => {
    if (!tenant) {
      return;
    }
    const mutationKey = `${member.username}:${roleName}`;
    setPendingRoleKey(mutationKey);
    setErrorMessage("");
    try {
      const updatedMember = checked
        ? await TenantService.assignTenantMemberRole(tenant.id, member.username, roleName)
        : await TenantService.removeTenantMemberRole(tenant.id, member.username, roleName);

      setMembers((currentMembers) =>
        currentMembers.map((currentMember) =>
          currentMember.username === member.username ? updatedMember : currentMember,
        ),
      );
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error) ||
          translate(
            "failed_to_update_organization_role",
            "Failed to update organization role.",
          ),
      );
    } finally {
      setPendingRoleKey(null);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      data-testid="tenant-role-dialog"
    >
      <DialogTitle>
        {translate("manage_organization_roles", "Manage Organization Roles")}
        {tenant ? `: ${tenant.name}` : ""}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {translate(
              "organization_role_management_description",
              "Assign tenant-scoped roles to members of this Keycloak organization. Only organization members are listed here.",
            )}
          </Typography>

          {errorMessage && <Alert severity="error">{errorMessage}</Alert>}

          <Box
            sx={{
              display: "flex",
              gap: 2,
              alignItems: "center",
            }}
          >
            <TextField
              fullWidth
              size="small"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={translate(
                "search_organization_members",
                "Search organization members...",
              )}
              data-testid="tenant-role-search-input"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />
            <Tooltip title={translate("refresh_members", "Refresh members")}>
              <span>
                <IconButton
                  onClick={loadMembers}
                  disabled={loading || !tenant}
                  data-testid="tenant-role-refresh-button"
                >
                  <RefreshIcon />
                </IconButton>
              </span>
            </Tooltip>
          </Box>

          <Paper variant="outlined">
            {loading ? (
              <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
                <CircularProgress />
              </Box>
            ) : filteredMembers.length === 0 ? (
              <Box sx={{ p: 4, textAlign: "center" }}>
                <Typography color="text.secondary">
                  {translate(
                    "no_organization_members_found",
                    "No organization members found.",
                  )}
                </Typography>
              </Box>
            ) : (
              <TableContainer sx={{ maxHeight: 520 }}>
                <Table stickyHeader size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{translate("username", "Username")}</TableCell>
                      <TableCell>{translate("display_name", "Display Name")}</TableCell>
                      <TableCell>{translate("email", "Email")}</TableCell>
                      {TENANT_ROLE_NAMES.map((roleName) => (
                        <TableCell key={roleName} align="center">
                          {roleLabel(roleName)}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredMembers.map((member) => (
                      <TableRow key={member.id || member.username} hover>
                        <TableCell>{member.username}</TableCell>
                        <TableCell>{member.display_name || "-"}</TableCell>
                        <TableCell>{member.email || "-"}</TableCell>
                        {TENANT_ROLE_NAMES.map((roleName) => {
                          const checked = member.roles.includes(roleName);
                          const mutationKey = `${member.username}:${roleName}`;
                          return (
                            <TableCell key={roleName} align="center">
                              <Checkbox
                                checked={checked}
                                disabled={pendingRoleKey === mutationKey}
                                onChange={(event) =>
                                  handleRoleToggle(member, roleName, event.target.checked)
                                }
                                inputProps={{
                                  "aria-label": `${member.username}-${roleName}`,
                                }}
                              />
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
