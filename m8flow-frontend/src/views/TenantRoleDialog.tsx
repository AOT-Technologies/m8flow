import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Checkbox,
  Collapse,
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
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import { useEffect, useMemo, useRef, useState } from "react";
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
const ADD_MEMBER_GROUP_NAME_MAX_WIDTH = 420;
const MEMBERS_PAGE_SIZE = 10;
const AVAILABLE_USERS_PAGE_SIZE = 10;
const DIALOG_TITLE_SX = { fontSize: "1.125rem", fontWeight: 600 } as const;
const SECTION_PANEL_BORDER_COLOR = "#CFE9E6";
const SECTION_HEADER_BACKGROUND_COLOR = "#DDF4F1";
const SECTION_PANEL_SX = {
  borderRadius: 2,
  border: "1px solid",
  borderColor: SECTION_PANEL_BORDER_COLOR,
  backgroundColor: "background.paper",
  overflow: "hidden",
} as const;
const SECTION_HEADER_SX = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  textAlign: "left",
  px: 2,
  py: 1.5,
  backgroundColor: SECTION_HEADER_BACKGROUND_COLOR,
} as const;
const SECTION_CONTENT_SX = {
  p: 2,
  backgroundColor: "background.paper",
} as const;

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
  const [memberSearchQuery, setMemberSearchQuery] = useState("");
  const [groupSearchQuery, setGroupSearchQuery] = useState("");
  const [groups, setGroups] = useState<TenantGroup[]>([]);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [isAddMemberDialogOpen, setIsAddMemberDialogOpen] = useState(false);
  const [isSubmittingMember, setIsSubmittingMember] = useState(false);
  const [addMemberErrorMessage, setAddMemberErrorMessage] = useState("");
  const [availableUserSearch, setAvailableUserSearch] = useState("");
  const [addMemberGroupSearch, setAddMemberGroupSearch] = useState("");
  const [availableUsers, setAvailableUsers] = useState<TenantAvailableUser[]>([]);
  const [availableUsersErrorMessage, setAvailableUsersErrorMessage] = useState("");
  const [isLoadingAvailableUsers, setIsLoadingAvailableUsers] = useState(false);
  const [availableUserPages, setAvailableUserPages] = useState<
    Record<number, TenantAvailableUser[]>
  >({});
  const [availableUserPageHasMore, setAvailableUserPageHasMore] = useState<
    Record<number, boolean>
  >({});
  const [currentAvailableUserPage, setCurrentAvailableUserPage] = useState(0);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [memberPages, setMemberPages] = useState<Record<number, TenantMember[]>>({});
  const [memberPageHasMore, setMemberPageHasMore] = useState<Record<number, boolean>>({});
  const [currentMemberPage, setCurrentMemberPage] = useState(0);
  const [isMembersSectionExpanded, setIsMembersSectionExpanded] = useState(true);
  const [isGroupsSectionExpanded, setIsGroupsSectionExpanded] = useState(false);
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
  const skipNextMemberSearchEffectRef = useRef(false);
  const skipNextAvailableUserSearchEffectRef = useRef(false);
  const activeMembersRequestTokenRef = useRef(0);
  const activeAvailableUsersRequestTokenRef = useRef(0);

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

  const resetMemberPagination = () => {
    setMembers([]);
    setMemberPages({});
    setMemberPageHasMore({});
    setCurrentMemberPage(0);
  };

  const resetAvailableUserPagination = () => {
    setAvailableUsers([]);
    setAvailableUserPages({});
    setAvailableUserPageHasMore({});
    setCurrentAvailableUserPage(0);
  };

  const loadTenantGroups = async () => {
    if (!tenant) {
      return;
    }
    setLoading(true);
    setErrorMessage("");
    try {
      const nextGroups = await TenantService.getTenantGroups(tenant.id);
      setGroups(nextGroups);
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

  const loadTenantMembers = async (
    search: string,
    options?: {
      page?: number;
    },
  ) => {
    if (!tenant) {
      return;
    }

    const page = Math.max(0, options?.page ?? 0);
    const normalizedSearch = search.trim();
    const requestToken = activeMembersRequestTokenRef.current + 1;

    activeMembersRequestTokenRef.current = requestToken;
    setIsLoadingMembers(true);
    setErrorMessage("");

    try {
      const nextMembersPage = await TenantService.getTenantMembersPage(
        tenant.id,
        {
          search: normalizedSearch,
          offset: page * MEMBERS_PAGE_SIZE,
          limit: MEMBERS_PAGE_SIZE,
        },
      );

      if (requestToken !== activeMembersRequestTokenRef.current) {
        return;
      }

      setMemberPages((currentPages) => ({
        ...currentPages,
        [page]: nextMembersPage.members,
      }));
      setMemberPageHasMore((currentPageHasMore) => ({
        ...currentPageHasMore,
        [page]: nextMembersPage.has_more,
      }));
      setMembers(nextMembersPage.members);
      setCurrentMemberPage(page);
    } catch (error: any) {
      if (requestToken !== activeMembersRequestTokenRef.current) {
        return;
      }
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_organization_members",
            "Failed to load tenant members.",
          ),
      );
    } finally {
      if (requestToken === activeMembersRequestTokenRef.current) {
        setIsLoadingMembers(false);
      }
    }
  };

  const refreshTenantAccessData = async () => {
    const pageToReload = currentMemberPage;
    resetMemberPagination();
    await Promise.all([
      loadTenantGroups(),
      loadTenantMembers(memberSearchQuery, { page: pageToReload }),
    ]);
  };

  useEffect(() => {
    if (!isVisible || !tenant) {
      setMemberSearchQuery("");
      setGroupSearchQuery("");
      setGroups([]);
      setMembers([]);
      setErrorMessage("");
      setIsAddMemberDialogOpen(false);
      setIsSubmittingMember(false);
      setAddMemberErrorMessage("");
      setAvailableUserSearch("");
      setAddMemberGroupSearch("");
      setAvailableUsers([]);
      setAvailableUsersErrorMessage("");
      setIsLoadingAvailableUsers(false);
      resetAvailableUserPagination();
      setIsLoadingMembers(false);
      resetMemberPagination();
      setIsMembersSectionExpanded(true);
      setIsGroupsSectionExpanded(false);
      setIsCreateGroupDialogOpen(false);
      setIsSubmittingGroup(false);
      setCreateGroupName("");
      setCreateGroupErrorMessage("");
      setIsCreateGroupNameTouched(false);
      setGroupMutationKey(null);
      setGroupRoleMutationKey(null);
      setMemberForm(emptyAddMemberForm());
      activeMembersRequestTokenRef.current += 1;
      activeAvailableUsersRequestTokenRef.current += 1;
      return;
    }
    skipNextMemberSearchEffectRef.current = true;
    resetMemberPagination();
    setIsMembersSectionExpanded(true);
    setIsGroupsSectionExpanded(false);
    void Promise.all([
      loadTenantGroups(),
      loadTenantMembers(memberSearchQuery, { page: 0 }),
    ]);
  }, [isVisible, tenant]);

  useEffect(() => {
    if (!isVisible || !tenant) {
      return;
    }

    if (skipNextMemberSearchEffectRef.current) {
      skipNextMemberSearchEffectRef.current = false;
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetMemberPagination();
      void loadTenantMembers(memberSearchQuery, { page: 0 });
    }, 200);

    return () => window.clearTimeout(timeoutId);
  }, [memberSearchQuery, isVisible, tenant]);

  const loadAvailableUsers = async (
    search = "",
    options?: {
      page?: number;
    },
  ) => {
    if (!tenant) {
      return;
    }
    const page = Math.max(0, options?.page ?? 0);
    const normalizedSearch = search.trim();
    const requestToken = activeAvailableUsersRequestTokenRef.current + 1;

    activeAvailableUsersRequestTokenRef.current = requestToken;
    setIsLoadingAvailableUsers(true);
    setAvailableUsersErrorMessage("");
    try {
      const nextUsersPage = await TenantService.getAvailableTenantUsersPage(
        tenant.id,
        {
          search: normalizedSearch,
          offset: page * AVAILABLE_USERS_PAGE_SIZE,
          limit: AVAILABLE_USERS_PAGE_SIZE,
        },
      );
      if (requestToken !== activeAvailableUsersRequestTokenRef.current) {
        return;
      }
      setAvailableUserPages((currentPages) => ({
        ...currentPages,
        [page]: nextUsersPage.users,
      }));
      setAvailableUserPageHasMore((currentPageHasMore) => ({
        ...currentPageHasMore,
        [page]: nextUsersPage.has_more,
      }));
      setAvailableUsers(nextUsersPage.users);
      setCurrentAvailableUserPage(page);
      setMemberForm((current) => ({
        ...current,
        username: nextUsersPage.users.some((user) => user.username === current.username)
          ? current.username
          : "",
      }));
    } catch (error: any) {
      if (requestToken !== activeAvailableUsersRequestTokenRef.current) {
        return;
      }
      setAvailableUsersErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_available_users",
            "Failed to load existing users.",
          ),
      );
    } finally {
      if (requestToken === activeAvailableUsersRequestTokenRef.current) {
        setIsLoadingAvailableUsers(false);
      }
    }
  };

  useEffect(() => {
    if (!isAddMemberDialogOpen || !tenant) {
      return;
    }
    skipNextAvailableUserSearchEffectRef.current = true;
    resetAvailableUserPagination();
    void loadAvailableUsers(availableUserSearch, { page: 0 });
  }, [isAddMemberDialogOpen, tenant]);

  useEffect(() => {
    if (!isAddMemberDialogOpen || !tenant) {
      return;
    }

    if (skipNextAvailableUserSearchEffectRef.current) {
      skipNextAvailableUserSearchEffectRef.current = false;
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetAvailableUserPagination();
      void loadAvailableUsers(availableUserSearch, { page: 0 });
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

  const canGoToPreviousMemberPage = currentMemberPage > 0;
  const canGoToNextMemberPage = Boolean(
    memberPages[currentMemberPage + 1]
      || memberPageHasMore[currentMemberPage],
  );
  const canGoToPreviousAvailableUserPage = currentAvailableUserPage > 0;
  const canGoToNextAvailableUserPage = Boolean(
    availableUserPages[currentAvailableUserPage + 1]
      || availableUserPageHasMore[currentAvailableUserPage],
  );

  const handleMemberPageChange = (nextPage: number) => {
    if (nextPage < 0 || nextPage === currentMemberPage) {
      return;
    }

    const cachedMembers = memberPages[nextPage];
    if (cachedMembers) {
      setCurrentMemberPage(nextPage);
      setMembers(cachedMembers);
      return;
    }

    if (nextPage > currentMemberPage && !memberPageHasMore[currentMemberPage]) {
      return;
    }

    void loadTenantMembers(memberSearchQuery, { page: nextPage });
  };

  const handleAvailableUserPageChange = (nextPage: number) => {
    if (nextPage < 0 || nextPage === currentAvailableUserPage) {
      return;
    }

    const cachedUsers = availableUserPages[nextPage];
    if (cachedUsers) {
      setCurrentAvailableUserPage(nextPage);
      setAvailableUsers(cachedUsers);
      setMemberForm((current) => ({
        ...current,
        username: cachedUsers.some((user) => user.username === current.username)
          ? current.username
          : "",
      }));
      return;
    }

    if (
      nextPage > currentAvailableUserPage
      && !availableUserPageHasMore[currentAvailableUserPage]
    ) {
      return;
    }

    void loadAvailableUsers(availableUserSearch, { page: nextPage });
  };

  const filteredGroups = useMemo(() => {
    const normalizedQuery = groupSearchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return groups;
    }

    return groups.filter((group) => {
      const roleValues = group.mapped_roles.flatMap((roleName) => [
        roleName.toLowerCase(),
        roleLabel(roleName).toLowerCase(),
      ]);
      return [group.name.toLowerCase(), ...roleValues].some((value) =>
        value.includes(normalizedQuery),
      );
    });
  }, [groupSearchQuery, groups, roleLabel]);

  const filteredAddMemberGroups = useMemo(() => {
    const normalizedQuery = addMemberGroupSearch.trim().toLowerCase();
    if (!normalizedQuery) {
      return groups;
    }

    return groups.filter((group) => {
      const roleValues = group.mapped_roles.flatMap((roleName) => [
        roleName.toLowerCase(),
        roleLabel(roleName).toLowerCase(),
      ]);
      return [group.name.toLowerCase(), ...roleValues].some((value) =>
        value.includes(normalizedQuery),
      );
    });
  }, [addMemberGroupSearch, groups, roleLabel]);

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
    setAddMemberGroupSearch("");
    resetAvailableUserPagination();
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
    setAddMemberGroupSearch("");
    activeAvailableUsersRequestTokenRef.current += 1;
    setIsLoadingAvailableUsers(false);
    resetAvailableUserPagination();
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
      await refreshTenantAccessData();
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
      await refreshTenantAccessData();
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
      await refreshTenantAccessData();
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
      await refreshTenantAccessData();
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
        <Typography
          variant="body1"
          color="text.secondary"
          sx={{ width: "100%", whiteSpace: "nowrap" }}
        >
          {translate(
            "tenant_group_management_description",
            "Add existing members and manage groups and roles associated with this tenant.",
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
              onClick={() => void refreshTenantAccessData()}
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
            <Box sx={SECTION_PANEL_SX}>
              <ButtonBase
                onClick={() =>
                  setIsMembersSectionExpanded((currentValue) => !currentValue)
                }
                data-testid="tenant-members-section-toggle"
                aria-expanded={isMembersSectionExpanded}
                aria-label={translate(
                  isMembersSectionExpanded
                    ? "collapse_members_section"
                    : "expand_members_section",
                  isMembersSectionExpanded ? "Collapse members" : "Expand members",
                )}
                sx={{
                  ...SECTION_HEADER_SX,
                  borderBottom: isMembersSectionExpanded ? "1px solid" : "none",
                  borderBottomColor: SECTION_PANEL_BORDER_COLOR,
                }}
              >
                <Typography variant="subtitle1" fontWeight={600}>
                  {translate("members", "Members")}
                </Typography>
                {isMembersSectionExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </ButtonBase>
              <Collapse in={isMembersSectionExpanded} unmountOnExit>
                <Box sx={SECTION_CONTENT_SX}>
                  <TextField
                    size="small"
                    value={memberSearchQuery}
                    onChange={(event) => setMemberSearchQuery(event.target.value)}
                    placeholder={translate(
                      "search_organization_members",
                      "Search tenant members...",
                    )}
                    sx={{ mb: 1.5, maxWidth: 360 }}
                    inputProps={{
                      ...testIdInputProps("tenant-member-search-input"),
                    }}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchIcon />
                        </InputAdornment>
                      ),
                    }}
                  />
                  {isLoadingMembers ? (
                    <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
                      <CircularProgress />
                    </Box>
                  ) : members.length === 0 ? (
                    <Box sx={{ py: 3, textAlign: "center" }}>
                      <Typography color="text.secondary">
                        {translate(
                          "no_organization_members_found",
                          "No tenant members found.",
                        )}
                      </Typography>
                    </Box>
                  ) : (
                    <Stack spacing={1.5}>
                      <TableContainer
                        sx={{
                          maxHeight: 360,
                          borderRadius: 1,
                          backgroundColor: "background.paper",
                        }}
                        data-testid="tenant-member-table-container"
                      >
                        <Table stickyHeader size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>{translate("username", "Username")}</TableCell>
                              <TableCell>
                                {translate("display_name", "Display Name")}
                              </TableCell>
                              <TableCell>{translate("email", "Email")}</TableCell>
                              {filteredGroups.map((group) => (
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
                            {members.map((member) => {
                              const memberGroups =
                                membershipLookup.get(member.username) ?? new Set<string>();
                              return (
                                <TableRow key={member.id || member.username} hover>
                                  <TableCell>{member.username}</TableCell>
                                  <TableCell>{member.display_name || "-"}</TableCell>
                                  <TableCell>{member.email || "-"}</TableCell>
                                  {filteredGroups.map((group) => {
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
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 2,
                        }}
                      >
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          data-testid="tenant-member-page-indicator"
                        >
                          {translate(
                            "tenant_members_page_indicator",
                            `Page ${currentMemberPage + 1}`,
                            { page: currentMemberPage + 1 },
                          )}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleMemberPageChange(currentMemberPage - 1)}
                            disabled={!canGoToPreviousMemberPage || isLoadingMembers}
                            data-testid="tenant-member-previous-page-button"
                          >
                            {translate("previous_page", "Previous")}
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleMemberPageChange(currentMemberPage + 1)}
                            disabled={!canGoToNextMemberPage || isLoadingMembers}
                            data-testid="tenant-member-next-page-button"
                          >
                            {translate("next_page", "Next")}
                          </Button>
                        </Stack>
                      </Box>
                    </Stack>
                  )}
                </Box>
              </Collapse>
            </Box>

            <Box sx={SECTION_PANEL_SX}>
              <ButtonBase
                onClick={() =>
                  setIsGroupsSectionExpanded((currentValue) => !currentValue)
                }
                data-testid="tenant-groups-section-toggle"
                aria-expanded={isGroupsSectionExpanded}
                aria-label={translate(
                  isGroupsSectionExpanded
                    ? "collapse_groups_section"
                    : "expand_groups_section",
                  isGroupsSectionExpanded ? "Collapse groups" : "Expand groups",
                )}
                sx={{
                  ...SECTION_HEADER_SX,
                  borderBottom: isGroupsSectionExpanded ? "1px solid" : "none",
                  borderBottomColor: SECTION_PANEL_BORDER_COLOR,
                }}
              >
                <Typography variant="subtitle1" fontWeight={600}>
                  {translate("groups", "Groups")}
                </Typography>
                {isGroupsSectionExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </ButtonBase>
              <Collapse in={isGroupsSectionExpanded} unmountOnExit>
                <Box sx={SECTION_CONTENT_SX}>
                <TextField
                  size="small"
                  value={groupSearchQuery}
                  onChange={(event) => setGroupSearchQuery(event.target.value)}
                  placeholder={translate(
                    "search_groups_or_roles",
                    "Search groups or roles...",
                  )}
                  sx={{ mb: 1.5, maxWidth: 360 }}
                  inputProps={{
                    ...testIdInputProps("tenant-group-search-input"),
                  }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon />
                      </InputAdornment>
                    ),
                  }}
                />
                {filteredGroups.length === 0 ? (
                  <Box sx={{ py: 3, textAlign: "center" }}>
                    <Typography color="text.secondary">
                      {groupSearchQuery.trim()
                        ? translate(
                            "no_matching_groups_or_roles_found",
                            "No groups or roles match your search.",
                          )
                        : translate(
                            "no_tenant_groups_found",
                            "No tenant groups found.",
                          )}
                    </Typography>
                  </Box>
                ) : (
                  <TableContainer
                    sx={{ maxHeight: 360, borderRadius: 1, backgroundColor: "background.paper" }}
                  >
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
              </Collapse>
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
          <DialogTitle sx={DIALOG_TITLE_SX}>
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
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("create_tenant_user", "Add User to Tenant")}
          {tenant ? `: ${tenant.name}` : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "add_tenant_user_description",
                "Add an existing user to this tenant, then assign groups.",
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

            <Stack spacing={1}>
              <TableContainer
                sx={{ maxHeight: 280 }}
                component={Paper}
                variant="outlined"
              >
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
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 2,
                }}
              >
                <Typography
                  variant="body2"
                  color="text.secondary"
                  data-testid="tenant-available-user-page-indicator"
                >
                  {translate(
                    "tenant_available_users_page_indicator",
                    `Page ${currentAvailableUserPage + 1}`,
                    { page: currentAvailableUserPage + 1 },
                  )}
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() =>
                      handleAvailableUserPageChange(currentAvailableUserPage - 1)
                    }
                    disabled={
                      !canGoToPreviousAvailableUserPage || isLoadingAvailableUsers
                    }
                    data-testid="tenant-available-user-previous-page-button"
                  >
                    {translate("previous_page", "Previous")}
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() =>
                      handleAvailableUserPageChange(currentAvailableUserPage + 1)
                    }
                    disabled={!canGoToNextAvailableUserPage || isLoadingAvailableUsers}
                    data-testid="tenant-available-user-next-page-button"
                  >
                    {translate("next_page", "Next")}
                  </Button>
                </Stack>
              </Box>
            </Stack>

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {translate("groups", "Groups")}
              </Typography>
              <TextField
                size="small"
                value={addMemberGroupSearch}
                onChange={(event) => setAddMemberGroupSearch(event.target.value)}
                placeholder={translate(
                  "search_groups_or_roles",
                  "Search groups or roles...",
                )}
                sx={{ mb: 1.5 }}
                inputProps={{
                  ...testIdInputProps("tenant-member-group-search-input"),
                }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
              />
              <Stack spacing={1}>
                {filteredAddMemberGroups.length === 0 ? (
                  <Typography color="text.secondary">
                    {translate(
                      "no_matching_groups_or_roles_found",
                      "No groups or roles match your search.",
                    )}
                  </Typography>
                ) : filteredAddMemberGroups.map((group) => (
                  <Box
                    key={group.id}
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                    }}
                  >
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
                    <Tooltip title={group.name}>
                      <Typography
                        component="span"
                        data-testid={`tenant-member-group-label-${group.id}`}
                        sx={{
                          ...truncatedValueSx,
                          maxWidth: ADD_MEMBER_GROUP_NAME_MAX_WIDTH,
                        }}
                      >
                        {group.name}
                      </Typography>
                    </Tooltip>
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
        <DialogTitle sx={DIALOG_TITLE_SX}>
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
