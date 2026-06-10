import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Paper,
  Radio,
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
import GroupAddIcon from "@mui/icons-material/GroupAdd";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import { useEffect, useMemo, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";
import TenantService, {
  normalizeTenantGroupName,
  TENANT_MEMBER_ROLES,
  TENANT_GROUP_NAME_MAX_LENGTH,
  Tenant,
  TenantAvailableUser,
  TenantGroup,
  TenantGroupMember,
  TenantMember,
  TenantMemberRole,
  validateTenantGroupName,
} from "../services/TenantService";

interface TenantRoleDialogProps {
  open?: boolean;
  tenant: Tenant | null;
  onClose: () => void;
  embedded?: boolean;
  showDescription?: boolean;
}

interface AddTenantMemberFormState {
  username: string;
  groupNames: string[];
}

function getErrorMessage(error: any): string {
  if (typeof error?.detail === "string" && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === "string" && error.message) {
    return error.message;
  }
  return "";
}

function emptyAddMemberForm(): AddTenantMemberFormState {
  return {
    username: "",
    groupNames: [],
  };
}

const MEMBER_MATRIX_GROUP_COLUMN_WIDTH = 160;
const GROUP_NAME_CELL_MAX_WIDTH = 240;

const truncatedValueSx = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
} as const;

const testIdInputProps = (
  testId: string,
): InputHTMLAttributes<HTMLInputElement> => ({
  "data-testid": testId,
});

export default function TenantRoleDialog({
  open = false,
  tenant,
  onClose,
  embedded = false,
  showDescription = true,
}: TenantRoleDialogProps) {
  const { t } = useTranslation();
  const isVisible = embedded ? Boolean(tenant) : open;
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [groups, setGroups] = useState<TenantGroup[]>([]);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [isAddMemberDialogOpen, setIsAddMemberDialogOpen] = useState(false);
  const [isSubmittingMember, setIsSubmittingMember] = useState(false);
  const [addMemberErrorMessage, setAddMemberErrorMessage] = useState("");
  const [availableUserSearch, setAvailableUserSearch] = useState("");
  const [availableUsers, setAvailableUsers] = useState<TenantAvailableUser[]>([]);
  const [availableUsersErrorMessage, setAvailableUsersErrorMessage] = useState("");
  const [isLoadingAvailableUsers, setIsLoadingAvailableUsers] = useState(false);
  const [isCreateGroupDialogOpen, setIsCreateGroupDialogOpen] = useState(false);
  const [isSubmittingGroup, setIsSubmittingGroup] = useState(false);
  const [createGroupName, setCreateGroupName] = useState("");
  const [createGroupErrorMessage, setCreateGroupErrorMessage] = useState("");
  const [isCreateGroupNameTouched, setIsCreateGroupNameTouched] = useState(false);
  const [groupMutationKey, setGroupMutationKey] = useState<string | null>(null);
  const [groupRoleMutationKey, setGroupRoleMutationKey] = useState<string | null>(null);
  const [memberForm, setMemberForm] = useState<AddTenantMemberFormState>(
    emptyAddMemberForm(),
  );

  const translate = (
    key: string,
    fallback: string,
    options?: Record<string, unknown>,
  ) => {
    const translated = t(key, options);
    return translated === key ? fallback : translated;
  };

  const roleLabel = (roleName: TenantMemberRole) =>
    translate(`tenant_role_${roleName.replace(/-/g, "_")}`, roleName);

  const loadTenantAccessData = async () => {
    if (!tenant) {
      return;
    }
    setLoading(true);
    setErrorMessage("");
    try {
      const [nextGroups, nextMembers] = await Promise.all([
        TenantService.getTenantGroups(tenant.id),
        TenantService.getTenantMembers(tenant.id),
      ]);
      setGroups(nextGroups);
      setMembers(nextMembers);
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_tenant_groups",
            "Failed to load tenant groups.",
          ),
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isVisible || !tenant) {
      setSearchQuery("");
      setGroups([]);
      setMembers([]);
      setErrorMessage("");
      setIsAddMemberDialogOpen(false);
      setIsSubmittingMember(false);
      setAddMemberErrorMessage("");
      setAvailableUserSearch("");
      setAvailableUsers([]);
      setAvailableUsersErrorMessage("");
      setIsLoadingAvailableUsers(false);
      setIsCreateGroupDialogOpen(false);
      setIsSubmittingGroup(false);
      setCreateGroupName("");
      setCreateGroupErrorMessage("");
      setIsCreateGroupNameTouched(false);
      setGroupMutationKey(null);
      setGroupRoleMutationKey(null);
      setMemberForm(emptyAddMemberForm());
      return;
    }
    void loadTenantAccessData();
  }, [isVisible, tenant]);

  const loadAvailableUsers = async (search = "") => {
    if (!tenant) {
      return;
    }
    setIsLoadingAvailableUsers(true);
    setAvailableUsersErrorMessage("");
    try {
      const nextUsers = await TenantService.getAvailableTenantUsers(tenant.id, search);
      setAvailableUsers(nextUsers);
      setMemberForm((current) => ({
        ...current,
        username: nextUsers.some((user) => user.username === current.username)
          ? current.username
          : "",
      }));
    } catch (error: any) {
      setAvailableUsersErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_available_users",
            "Failed to load existing users.",
          ),
      );
    } finally {
      setIsLoadingAvailableUsers(false);
    }
  };

  useEffect(() => {
    if (!isAddMemberDialogOpen || !tenant) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      void loadAvailableUsers(availableUserSearch);
    }, 200);

    return () => window.clearTimeout(timeoutId);
  }, [availableUserSearch, isAddMemberDialogOpen, tenant]);

  const membershipLookup = useMemo(() => {
    const lookup = new Map<string, Set<string>>();
    groups.forEach((group) => {
      group.members.forEach((member: TenantGroupMember) => {
        const memberKey = member.username;
        if (!lookup.has(memberKey)) {
          lookup.set(memberKey, new Set<string>());
        }
        lookup.get(memberKey)?.add(group.name);
      });
    });
    return lookup;
  }, [groups]);

  const filteredMembers = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return members;
    }

    return members.filter((member) => {
      const assignedGroupNames = Array.from(
        membershipLookup.get(member.username) ?? new Set<string>(),
      );
      const values = [
        member.username,
        member.display_name ?? "",
        member.email ?? "",
        ...assignedGroupNames,
      ]
        .filter(Boolean)
        .map((value) => value.toLowerCase());
      return values.some((value) => value.includes(normalizedQuery));
    });
  }, [members, membershipLookup, searchQuery]);

  const filteredGroups = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return groups;
    }

    return groups.filter((group) => {
      const roleLabels = group.mapped_roles.map((roleName) =>
        roleLabel(roleName).toLowerCase(),
      );
      const memberValues = group.members.flatMap((member) =>
        [member.username, member.display_name ?? "", member.email ?? ""].map(
          (value) => value.toLowerCase(),
        ),
      );
      return [
        group.name.toLowerCase(),
        (group.path ?? "").toLowerCase(),
        ...roleLabels,
        ...memberValues,
      ].some((value) => value.includes(normalizedQuery));
    });
  }, [groups, roleLabel, searchQuery]);

  const createGroupValidationMessage = useMemo(() => {
    const validationMessage = validateTenantGroupName(createGroupName);
    if (validationMessage) {
      return validationMessage;
    }

    const normalizedGroupName = normalizeTenantGroupName(createGroupName);
    const duplicateGroup = groups.some(
      (group) =>
        normalizeTenantGroupName(group.name).toLowerCase()
        === normalizedGroupName.toLowerCase(),
    );
    if (duplicateGroup) {
      return translate(
        "tenant_group_name_exists",
        `Group '${normalizedGroupName}' already exists in this tenant.`,
      );
    }

    return "";
  }, [createGroupName, groups, translate]);

  const handleOpenAddMemberDialog = () => {
    setMemberForm(emptyAddMemberForm());
    setAddMemberErrorMessage("");
    setAvailableUserSearch("");
    setAvailableUsers([]);
    setAvailableUsersErrorMessage("");
    setIsAddMemberDialogOpen(true);
  };

  const handleCloseAddMemberDialog = () => {
    if (isSubmittingMember) {
      return;
    }
    setIsAddMemberDialogOpen(false);
    setAddMemberErrorMessage("");
    setAvailableUserSearch("");
    setAvailableUsers([]);
    setAvailableUsersErrorMessage("");
    setMemberForm(emptyAddMemberForm());
  };

  const handleOpenCreateGroupDialog = () => {
    setCreateGroupName("");
    setCreateGroupErrorMessage("");
    setIsCreateGroupNameTouched(false);
    setIsCreateGroupDialogOpen(true);
  };

  const handleCloseCreateGroupDialog = () => {
    if (isSubmittingGroup) {
      return;
    }
    setIsCreateGroupDialogOpen(false);
    setCreateGroupName("");
    setCreateGroupErrorMessage("");
    setIsCreateGroupNameTouched(false);
  };

  const handleToggleAddMemberGroup = (groupName: string) => {
    setMemberForm((current) => {
      const groupNames = current.groupNames.includes(groupName)
        ? current.groupNames.filter((name) => name !== groupName)
        : [...current.groupNames, groupName];
      return {
        ...current,
        groupNames,
      };
    });
  };

  const handleCreateTenantMember = async () => {
    if (!tenant) {
      return;
    }
    setIsSubmittingMember(true);
    setAddMemberErrorMessage("");
    try {
      await TenantService.addTenantMember(tenant.id, {
        username: memberForm.username,
        group_names: memberForm.groupNames,
      });
      handleCloseAddMemberDialog();
      await loadTenantAccessData();
    } catch (error: any) {
      setAddMemberErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_add_tenant_member",
            "Failed to add user to tenant.",
          ),
      );
    } finally {
      setIsSubmittingMember(false);
    }
  };

  const handleCreateTenantGroup = async () => {
    if (!tenant) {
      return;
    }
    if (createGroupValidationMessage) {
      setIsCreateGroupNameTouched(true);
      return;
    }

    setIsSubmittingGroup(true);
    setCreateGroupErrorMessage("");
    try {
      await TenantService.createTenantGroup(tenant.id, {
        name: normalizeTenantGroupName(createGroupName),
      });
      handleCloseCreateGroupDialog();
      await loadTenantAccessData();
    } catch (error: any) {
      setCreateGroupErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_create_tenant_group",
            "Failed to create tenant group.",
          ),
      );
    } finally {
      setIsSubmittingGroup(false);
    }
  };

  const handleToggleGroupMembership = async (
    member: TenantMember,
    group: TenantGroup,
    shouldBeMember: boolean,
  ) => {
    if (!tenant) {
      return;
    }
    const mutationKey = `${member.username}:${group.name}`;
    setGroupMutationKey(mutationKey);
    setErrorMessage("");
    try {
      if (shouldBeMember) {
        await TenantService.addTenantMemberToGroup(
          tenant.id,
          member.username,
          group.name,
        );
      } else {
        await TenantService.removeTenantMemberFromGroup(
          tenant.id,
          member.username,
          group.name,
        );
      }
      await loadTenantAccessData();
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_update_group_membership",
            "Failed to update tenant group membership.",
          ),
      );
    } finally {
      setGroupMutationKey(null);
    }
  };

  const handleToggleGroupRole = async (
    group: TenantGroup,
    roleName: TenantMemberRole,
    shouldBeAssigned: boolean,
  ) => {
    if (!tenant) {
      return;
    }
    const mutationKey = `${group.name}:${roleName}`;
    setGroupRoleMutationKey(mutationKey);
    setErrorMessage("");
    try {
      if (shouldBeAssigned) {
        await TenantService.assignTenantGroupRole(tenant.id, group.name, roleName);
      } else {
        await TenantService.removeTenantGroupRole(tenant.id, group.name, roleName);
      }
      await loadTenantAccessData();
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_update_group_role",
            "Failed to update tenant group role mapping.",
          ),
      );
    } finally {
      setGroupRoleMutationKey(null);
    }
  };

  const managementContent = (
    <Stack spacing={2} sx={embedded ? undefined : { mt: 1 }}>
      {showDescription && (
        <Typography variant="body2" color="text.secondary">
          {translate(
            "tenant_group_management_description",
            "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
          )}
        </Typography>
      )}

      {errorMessage && <Alert severity="error">{errorMessage}</Alert>}

      <Box
        sx={{
          display: "flex",
          gap: 2,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <TextField
          fullWidth
          size="small"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={translate(
            "search_tenant_groups",
            "Search tenant groups or members...",
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
        <Button
          variant="contained"
          startIcon={<PersonAddAlt1Icon />}
          onClick={handleOpenAddMemberDialog}
          disabled={!tenant || loading}
          data-testid="tenant-member-add-button"
        >
          {translate("add_tenant_user", "Add User")}
        </Button>
        <Button
          variant="outlined"
          startIcon={<GroupAddIcon />}
          onClick={handleOpenCreateGroupDialog}
          disabled={!tenant || loading}
          data-testid="tenant-group-add-button"
        >
          {translate("create_group", "Create Group")}
        </Button>
        <Tooltip
          title={translate("refresh_tenant_groups", "Refresh tenant groups")}
        >
          <span>
            <IconButton
              onClick={() => void loadTenantAccessData()}
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
        ) : (
          <Stack spacing={3} sx={{ p: 2 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
                {translate("members", "Members")}
              </Typography>
              {filteredMembers.length === 0 ? (
                <Box sx={{ py: 3, textAlign: "center" }}>
                  <Typography color="text.secondary">
                    {translate(
                      "no_organization_members_found",
                      "No tenant members found.",
                    )}
                  </Typography>
                </Box>
              ) : (
                <TableContainer sx={{ maxHeight: 360 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{translate("username", "Username")}</TableCell>
                        <TableCell>
                          {translate("display_name", "Display Name")}
                        </TableCell>
                        <TableCell>{translate("email", "Email")}</TableCell>
                        {groups.map((group) => (
                          <TableCell
                            key={group.id}
                            align="center"
                            sx={{
                              width: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                              minWidth: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                              maxWidth: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                            }}
                          >
                            <Tooltip title={group.name}>
                              <Typography
                                data-testid={`tenant-members-group-header-${group.id}`}
                                sx={{
                                  ...truncatedValueSx,
                                  maxWidth: MEMBER_MATRIX_GROUP_COLUMN_WIDTH - 24,
                                }}
                              >
                                {group.name}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredMembers.map((member) => {
                        const memberGroups =
                          membershipLookup.get(member.username) ?? new Set<string>();
                        return (
                          <TableRow key={member.id || member.username} hover>
                            <TableCell>{member.username}</TableCell>
                            <TableCell>{member.display_name || "-"}</TableCell>
                            <TableCell>{member.email || "-"}</TableCell>
                            {groups.map((group) => {
                              const mutationKey = `${member.username}:${group.name}`;
                              const checked = memberGroups.has(group.name);
                              return (
                                <TableCell
                                  key={`${member.username}:${group.id}`}
                                  align="center"
                                  sx={{
                                    width: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                                    minWidth: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                                    maxWidth: MEMBER_MATRIX_GROUP_COLUMN_WIDTH,
                                  }}
                                >
                                  <Checkbox
                                    checked={checked}
                                    disabled={groupMutationKey === mutationKey || loading}
                                    onChange={(event) =>
                                      void handleToggleGroupMembership(
                                        member,
                                        group,
                                        event.target.checked,
                                      )
                                    }
                                    inputProps={{
                                      ...testIdInputProps(
                                        `tenant-group-checkbox-${member.username}-${group.name}`,
                                      ),
                                    }}
                                  />
                                </TableCell>
                              );
                            })}
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Box>

            <Box>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
                {translate("groups", "Groups")}
              </Typography>
              {filteredGroups.length === 0 ? (
                <Box sx={{ py: 3, textAlign: "center" }}>
                  <Typography color="text.secondary">
                    {translate(
                      "no_tenant_groups_found",
                      "No tenant groups found.",
                    )}
                  </Typography>
                </Box>
              ) : (
                <TableContainer sx={{ maxHeight: 360 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{translate("group", "Group")}</TableCell>
                        <TableCell>
                          {translate("granted_roles", "Granted Roles")}
                        </TableCell>
                        <TableCell>{translate("members", "Members")}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredGroups.map((group) => (
                        <TableRow key={group.id} hover>
                          <TableCell sx={{ width: GROUP_NAME_CELL_MAX_WIDTH }}>
                            <Tooltip title={group.name}>
                              <Typography
                                data-testid={`tenant-group-name-cell-${group.id}`}
                                fontWeight={600}
                                sx={{
                                  ...truncatedValueSx,
                                  maxWidth: GROUP_NAME_CELL_MAX_WIDTH,
                                }}
                              >
                                {group.name}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                              {TENANT_MEMBER_ROLES.map((roleName) => {
                                const mutationKey = `${group.name}:${roleName}`;
                                const checked = group.mapped_roles.includes(roleName);
                                return (
                                  <FormControlLabel
                                    key={`${group.id}:${roleName}`}
                                    sx={{ mr: 1 }}
                                    control={
                                      <Checkbox
                                        size="small"
                                        checked={checked}
                                        disabled={loading || groupRoleMutationKey === mutationKey}
                                        onChange={(event) =>
                                          void handleToggleGroupRole(
                                            group,
                                            roleName,
                                            event.target.checked,
                                          )
                                        }
                                        inputProps={{
                                          ...testIdInputProps(
                                            `tenant-group-role-checkbox-${group.name}-${roleName}`,
                                          ),
                                        }}
                                      />
                                    }
                                    label={roleLabel(roleName)}
                                  />
                                );
                              })}
                            </Stack>
                          </TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                              {group.members.length > 0 ? (
                                group.members.map((member) => (
                                  <Chip
                                    key={member.id || member.username}
                                    size="small"
                                    label={member.username}
                                    variant="outlined"
                                  />
                                ))
                              ) : (
                                <Typography color="text.secondary">-</Typography>
                              )}
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Box>
          </Stack>
        )}
      </Paper>
    </Stack>
  );

  return (
    <>
      {embedded ? (
        <Box data-testid="tenant-role-panel">{managementContent}</Box>
      ) : (
        <Dialog
          open={open}
          onClose={onClose}
          fullWidth
          maxWidth="lg"
          data-testid="tenant-role-dialog"
        >
          <DialogTitle>
            {translate("manage_tenant_groups", "Manage Tenant Groups")}
            {tenant ? `: ${tenant.name}` : ""}
          </DialogTitle>
          <DialogContent>{managementContent}</DialogContent>
        </Dialog>
      )}

      <Dialog
        open={isAddMemberDialogOpen}
        onClose={handleCloseAddMemberDialog}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {translate("create_tenant_user", "Add User to Tenant")}
          {tenant ? `: ${tenant.name}` : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "add_tenant_user_description",
                "Add an existing user to this tenant, then assign Keycloak groups.",
              )}
            </Typography>

            {addMemberErrorMessage && (
              <Alert severity="error">{addMemberErrorMessage}</Alert>
            )}

            {availableUsersErrorMessage && (
              <Alert severity="error">{availableUsersErrorMessage}</Alert>
            )}

            <TextField
              label={translate("existing_user", "Existing User")}
              value={availableUserSearch}
              onChange={(event) => setAvailableUserSearch(event.target.value)}
              placeholder={translate(
                "search_existing_users",
                "Search existing users...",
              )}
              inputProps={{
                ...testIdInputProps("tenant-member-existing-user-search-input"),
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />

            <TableContainer sx={{ maxHeight: 280 }} component={Paper} variant="outlined">
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 56 }} />
                    <TableCell>{translate("username", "Username")}</TableCell>
                    <TableCell>
                      {translate("display_name", "Display Name")}
                    </TableCell>
                    <TableCell>{translate("email", "Email")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {isLoadingAvailableUsers ? (
                    <TableRow>
                      <TableCell colSpan={4} align="center">
                        <Box sx={{ py: 3 }}>
                          <CircularProgress size={24} />
                        </Box>
                      </TableCell>
                    </TableRow>
                  ) : availableUsers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} align="center">
                        <Typography color="text.secondary" sx={{ py: 2 }}>
                          {translate(
                            "no_available_users_found",
                            "No existing users available to add.",
                          )}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    availableUsers.map((user) => (
                      <TableRow
                        key={user.id || user.username}
                        hover
                        selected={memberForm.username === user.username}
                        onClick={() =>
                          setMemberForm((current) => ({
                            ...current,
                            username: user.username,
                          }))
                        }
                        sx={{ cursor: "pointer" }}
                      >
                        <TableCell padding="checkbox">
                          <Radio
                            checked={memberForm.username === user.username}
                            onChange={() =>
                              setMemberForm((current) => ({
                                ...current,
                                username: user.username,
                              }))
                            }
                            value={user.username}
                            inputProps={{
                              ...testIdInputProps(
                                `tenant-member-existing-user-option-${user.username}`,
                              ),
                            }}
                          />
                        </TableCell>
                        <TableCell>{user.username}</TableCell>
                        <TableCell>{user.display_name || "-"}</TableCell>
                        <TableCell>{user.email || "-"}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {translate("groups", "Groups")}
              </Typography>
              <Stack spacing={1}>
                {groups.map((group) => (
                  <Box key={group.id}>
                    <Checkbox
                      checked={memberForm.groupNames.includes(group.name)}
                      onChange={() => handleToggleAddMemberGroup(group.name)}
                      disabled={isSubmittingMember}
                      inputProps={{
                        ...testIdInputProps(
                          `tenant-member-group-option-${group.name}`,
                        ),
                      }}
                    />
                    <Typography component="span">{group.name}</Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseAddMemberDialog} disabled={isSubmittingMember}>
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleCreateTenantMember()}
            disabled={isSubmittingMember || !memberForm.username}
            data-testid="tenant-member-submit-button"
          >
            {isSubmittingMember
              ? translate("processing", "Processing...")
              : translate("add", "Add")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={isCreateGroupDialogOpen}
        onClose={handleCloseCreateGroupDialog}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {translate("create_group", "Create Group")}
          {tenant ? `: ${tenant.name}` : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "create_group_description",
                "Create a new Keycloak group for this tenant. Tenant roles can be assigned after creation.",
              )}
            </Typography>
            {createGroupErrorMessage && (
              <Alert severity="error">{createGroupErrorMessage}</Alert>
            )}
            <TextField
              label={translate("group_name", "Group Name")}
              value={createGroupName}
              onChange={(event) => {
                setCreateGroupName(event.target.value);
                setIsCreateGroupNameTouched(true);
                if (createGroupErrorMessage) {
                  setCreateGroupErrorMessage("");
                }
              }}
              onBlur={() => {
                setIsCreateGroupNameTouched(true);
                setCreateGroupName((current) => normalizeTenantGroupName(current));
              }}
              error={isCreateGroupNameTouched && Boolean(createGroupValidationMessage)}
              helperText={
                isCreateGroupNameTouched && createGroupValidationMessage
                  ? createGroupValidationMessage
                  : translate(
                      "tenant_group_name_helper",
                      `Up to ${TENANT_GROUP_NAME_MAX_LENGTH} characters. Letters, numbers, spaces, hyphens, and underscores only.`,
                    )
              }
              inputProps={{
                maxLength: TENANT_GROUP_NAME_MAX_LENGTH,
                ...testIdInputProps("tenant-group-name-input"),
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseCreateGroupDialog} disabled={isSubmittingGroup}>
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleCreateTenantGroup()}
            disabled={
              isSubmittingGroup
              || !createGroupName.trim()
              || Boolean(createGroupValidationMessage)
            }
            data-testid="tenant-group-submit-button"
          >
            {isSubmittingGroup
              ? translate("processing", "Processing...")
              : translate("create", "Create")}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
