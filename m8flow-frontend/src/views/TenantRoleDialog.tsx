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
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import GroupAddIcon from "@mui/icons-material/GroupAdd";
import ManageAccountsIcon from "@mui/icons-material/ManageAccounts";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
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

const GROUP_NAME_CELL_MAX_WIDTH = 240;
const ADD_MEMBER_GROUP_NAME_MAX_WIDTH = 420;
const MEMBERS_PAGE_SIZE = 10;
const GROUPS_PAGE_SIZE = 10;
const AVAILABLE_USERS_PAGE_SIZE = 10;
const MEMBER_GROUPS_CELL_MAX_WIDTH = 320;
const MEMBER_EFFECTIVE_ROLES_CELL_MAX_WIDTH = 320;
const MEMBER_ACTIONS_CELL_WIDTH = 120;
const GROUP_GRANTED_ROLES_CELL_MAX_WIDTH = 360;
const GROUP_ACTIONS_CELL_WIDTH = 152;
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
const SECTION_HEADER_TOGGLE_SX = {
  flex: "1 1 220px",
  minWidth: 0,
  justifyContent: "flex-start",
  textAlign: "left",
  px: 0,
  py: 0.5,
  borderRadius: 1,
} as const;
const SECTION_TOOLBAR_SX = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 2,
  flexWrap: "wrap",
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
  const [memberSearchQuery, setMemberSearchQuery] = useState("");
  const [groupSearchQuery, setGroupSearchQuery] = useState("");
  const [groups, setGroups] = useState<TenantGroup[]>([]);
  const [allGroups, setAllGroups] = useState<TenantGroup[]>([]);
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
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);
  const [groupPages, setGroupPages] = useState<Record<number, TenantGroup[]>>({});
  const [groupPageHasMore, setGroupPageHasMore] = useState<Record<number, boolean>>({});
  const [currentGroupPage, setCurrentGroupPage] = useState(0);
  const [isLoadingAllGroups, setIsLoadingAllGroups] = useState(false);
  const [hasLoadedAllGroups, setHasLoadedAllGroups] = useState(false);
  const [isMembersSectionExpanded, setIsMembersSectionExpanded] = useState(true);
  const [isGroupsSectionExpanded, setIsGroupsSectionExpanded] = useState(false);
  const [isCreateGroupDialogOpen, setIsCreateGroupDialogOpen] = useState(false);
  const [isSubmittingGroup, setIsSubmittingGroup] = useState(false);
  const [createGroupName, setCreateGroupName] = useState("");
  const [createGroupErrorMessage, setCreateGroupErrorMessage] = useState("");
  const [isCreateGroupNameTouched, setIsCreateGroupNameTouched] = useState(false);
  const [selectedGroupForRename, setSelectedGroupForRename] = useState<TenantGroup | null>(null);
  const [renameGroupName, setRenameGroupName] = useState("");
  const [renameGroupErrorMessage, setRenameGroupErrorMessage] = useState("");
  const [isRenameGroupNameTouched, setIsRenameGroupNameTouched] = useState(false);
  const [isSubmittingGroupRename, setIsSubmittingGroupRename] = useState(false);
  const [selectedMemberForGroupManagement, setSelectedMemberForGroupManagement] = useState<TenantMember | null>(null);
  const [selectedGroupForRoleManagement, setSelectedGroupForRoleManagement] = useState<TenantGroup | null>(null);
  const [memberPendingRemoval, setMemberPendingRemoval] = useState<TenantMember | null>(null);
  const [groupPendingRemoval, setGroupPendingRemoval] = useState<TenantGroup | null>(null);
  const [memberRemovalUsername, setMemberRemovalUsername] = useState<string | null>(null);
  const [groupRemovalName, setGroupRemovalName] = useState<string | null>(null);
  const [groupMutationKey, setGroupMutationKey] = useState<string | null>(null);
  const [groupRoleMutationKey, setGroupRoleMutationKey] = useState<string | null>(null);
  const [memberForm, setMemberForm] = useState<AddTenantMemberFormState>(
    emptyAddMemberForm(),
  );
  const skipNextMemberSearchEffectRef = useRef(false);
  const skipNextGroupSearchEffectRef = useRef(false);
  const skipNextAvailableUserSearchEffectRef = useRef(false);
  const activeMembersRequestTokenRef = useRef(0);
  const activeGroupsRequestTokenRef = useRef(0);
  const activeAllGroupsRequestTokenRef = useRef(0);
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

  const resetGroupPagination = () => {
    setGroups([]);
    setGroupPages({});
    setGroupPageHasMore({});
    setCurrentGroupPage(0);
  };

  const resetAvailableUserPagination = () => {
    setAvailableUsers([]);
    setAvailableUserPages({});
    setAvailableUserPageHasMore({});
    setCurrentAvailableUserPage(0);
  };

  const loadTenantGroupsPage = async (
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
    const requestToken = activeGroupsRequestTokenRef.current + 1;

    activeGroupsRequestTokenRef.current = requestToken;
    setIsLoadingGroups(true);
    setErrorMessage("");
    try {
      const nextGroupsPage = await TenantService.getTenantGroupsPage(
        tenant.id,
        {
          search: normalizedSearch,
          offset: page * GROUPS_PAGE_SIZE,
          limit: GROUPS_PAGE_SIZE,
        },
      );

      if (requestToken !== activeGroupsRequestTokenRef.current) {
        return;
      }

      setGroupPages((currentPages) => ({
        ...currentPages,
        [page]: nextGroupsPage.groups,
      }));
      setGroupPageHasMore((currentPageHasMore) => ({
        ...currentPageHasMore,
        [page]: nextGroupsPage.has_more,
      }));
      setGroups(nextGroupsPage.groups);
      setCurrentGroupPage(page);
    } catch (error: any) {
      if (requestToken !== activeGroupsRequestTokenRef.current) {
        return;
      }
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_tenant_groups",
            "Failed to load tenant groups.",
          ),
      );
    } finally {
      if (requestToken === activeGroupsRequestTokenRef.current) {
        setIsLoadingGroups(false);
      }
    }
  };

  const loadAllTenantGroups = async (options?: { force?: boolean }) => {
    if (!tenant) {
      return;
    }
    if (!options?.force && (hasLoadedAllGroups || isLoadingAllGroups)) {
      return;
    }

    const requestToken = activeAllGroupsRequestTokenRef.current + 1;

    activeAllGroupsRequestTokenRef.current = requestToken;
    setIsLoadingAllGroups(true);
    setErrorMessage("");
    try {
      const nextGroups = await TenantService.getTenantGroups(tenant.id);

      if (requestToken !== activeAllGroupsRequestTokenRef.current) {
        return;
      }

      setAllGroups(nextGroups);
      setHasLoadedAllGroups(true);
    } catch (error: any) {
      if (requestToken !== activeAllGroupsRequestTokenRef.current) {
        return;
      }
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_load_tenant_groups",
            "Failed to load tenant groups.",
          ),
      );
    } finally {
      if (requestToken === activeAllGroupsRequestTokenRef.current) {
        setIsLoadingAllGroups(false);
      }
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
    const memberPageToReload = currentMemberPage;
    const groupPageToReload = currentGroupPage;
    resetMemberPagination();
    resetGroupPagination();
    await Promise.all([
      loadTenantGroupsPage(groupSearchQuery, { page: groupPageToReload }),
      loadTenantMembers(memberSearchQuery, { page: memberPageToReload }),
      (
        hasLoadedAllGroups
          || isAddMemberDialogOpen
          || isCreateGroupDialogOpen
          || Boolean(selectedMemberForGroupManagement)
      )
        ? loadAllTenantGroups({ force: true })
        : Promise.resolve(),
    ]);
  };

  useEffect(() => {
    if (!isVisible || !tenant) {
      setMemberSearchQuery("");
      setGroupSearchQuery("");
      setGroups([]);
      setAllGroups([]);
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
      setIsLoadingGroups(false);
      resetGroupPagination();
      setIsLoadingAllGroups(false);
      setHasLoadedAllGroups(false);
      setIsMembersSectionExpanded(true);
      setIsGroupsSectionExpanded(false);
      setIsCreateGroupDialogOpen(false);
      setIsSubmittingGroup(false);
      setCreateGroupName("");
      setCreateGroupErrorMessage("");
      setIsCreateGroupNameTouched(false);
      setSelectedGroupForRename(null);
      setRenameGroupName("");
      setRenameGroupErrorMessage("");
      setIsRenameGroupNameTouched(false);
      setIsSubmittingGroupRename(false);
      setSelectedMemberForGroupManagement(null);
      setSelectedGroupForRoleManagement(null);
      setMemberPendingRemoval(null);
      setGroupPendingRemoval(null);
      setMemberRemovalUsername(null);
      setGroupRemovalName(null);
      setGroupMutationKey(null);
      setGroupRoleMutationKey(null);
      setMemberForm(emptyAddMemberForm());
      activeMembersRequestTokenRef.current += 1;
      activeGroupsRequestTokenRef.current += 1;
      activeAllGroupsRequestTokenRef.current += 1;
      activeAvailableUsersRequestTokenRef.current += 1;
      return;
    }
    skipNextMemberSearchEffectRef.current = true;
    skipNextGroupSearchEffectRef.current = true;
    resetMemberPagination();
    resetGroupPagination();
    setIsMembersSectionExpanded(true);
    setIsGroupsSectionExpanded(false);
    void Promise.all([
      loadTenantGroupsPage(groupSearchQuery, { page: 0 }),
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

  useEffect(() => {
    if (!isVisible || !tenant) {
      return;
    }

    if (skipNextGroupSearchEffectRef.current) {
      skipNextGroupSearchEffectRef.current = false;
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetGroupPagination();
      void loadTenantGroupsPage(groupSearchQuery, { page: 0 });
    }, 200);

    return () => window.clearTimeout(timeoutId);
  }, [groupSearchQuery, isVisible, tenant]);

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

  const selectedMemberForGroupManagementCurrent = useMemo(() => {
    if (!selectedMemberForGroupManagement) {
      return null;
    }

    return members.find(
      (member) =>
        member.id === selectedMemberForGroupManagement.id
        || member.username === selectedMemberForGroupManagement.username,
    ) ?? selectedMemberForGroupManagement;
  }, [members, selectedMemberForGroupManagement]);

  const selectedGroupForRoleManagementCurrent = useMemo(() => {
    if (!selectedGroupForRoleManagement) {
      return null;
    }

    return groups.find((group) => group.id === selectedGroupForRoleManagement.id) ?? null;
  }, [groups, selectedGroupForRoleManagement]);

  const selectedGroupForRenameCurrent = useMemo(() => {
    if (!selectedGroupForRename) {
      return null;
    }

    return (
      groups.find((group) => group.id === selectedGroupForRename.id)
      ?? allGroups.find((group) => group.id === selectedGroupForRename.id)
      ?? selectedGroupForRename
    );
  }, [allGroups, groups, selectedGroupForRename]);

  const canGoToPreviousMemberPage = currentMemberPage > 0;
  const canGoToNextMemberPage = Boolean(
    memberPages[currentMemberPage + 1]
      || memberPageHasMore[currentMemberPage],
  );
  const canGoToPreviousGroupPage = currentGroupPage > 0;
  const canGoToNextGroupPage = Boolean(
    groupPages[currentGroupPage + 1]
      || groupPageHasMore[currentGroupPage],
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

  const handleGroupPageChange = (nextPage: number) => {
    if (nextPage < 0 || nextPage === currentGroupPage) {
      return;
    }

    const cachedGroups = groupPages[nextPage];
    if (cachedGroups) {
      setCurrentGroupPage(nextPage);
      setGroups(cachedGroups);
      return;
    }

    if (nextPage > currentGroupPage && !groupPageHasMore[currentGroupPage]) {
      return;
    }

    void loadTenantGroupsPage(groupSearchQuery, { page: nextPage });
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

  const toggleMembersSection = () => {
    setIsMembersSectionExpanded((currentValue) => !currentValue);
  };

  const toggleGroupsSection = () => {
    setIsGroupsSectionExpanded((currentValue) => !currentValue);
  };

  const filteredAddMemberGroups = useMemo(() => {
    const normalizedQuery = addMemberGroupSearch.trim().toLowerCase();
    if (!normalizedQuery) {
      return allGroups;
    }

    return allGroups.filter((group) => {
      const roleValues = group.mapped_roles.flatMap((roleName) => [
        roleName.toLowerCase(),
        roleLabel(roleName).toLowerCase(),
      ]);
      return [group.name.toLowerCase(), ...roleValues].some((value) =>
        value.includes(normalizedQuery),
      );
    });
  }, [addMemberGroupSearch, allGroups, roleLabel]);

  const createGroupValidationMessage = useMemo(() => {
    const validationMessage = validateTenantGroupName(createGroupName);
    if (validationMessage) {
      return validationMessage;
    }

    const normalizedGroupName = normalizeTenantGroupName(createGroupName);
    const duplicateGroup = allGroups.some(
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
  }, [allGroups, createGroupName, translate]);

  const renameGroupValidationMessage = useMemo(() => {
    const validationMessage = validateTenantGroupName(renameGroupName);
    if (validationMessage) {
      return validationMessage;
    }

    const normalizedGroupName = normalizeTenantGroupName(renameGroupName);
    const selectedGroupId = selectedGroupForRenameCurrent?.id ?? selectedGroupForRename?.id;
    const duplicateGroup = allGroups.some(
      (group) =>
        group.id !== selectedGroupId
        && normalizeTenantGroupName(group.name).toLowerCase()
          === normalizedGroupName.toLowerCase(),
    );
    if (duplicateGroup) {
      return translate(
        "tenant_group_name_exists",
        `Group '${normalizedGroupName}' already exists in this tenant.`,
      );
    }

    return "";
  }, [
    allGroups,
    renameGroupName,
    selectedGroupForRename,
    selectedGroupForRenameCurrent,
    translate,
  ]);

  const isRenameGroupUnchanged = useMemo(() => {
    if (!selectedGroupForRenameCurrent) {
      return true;
    }

    return normalizeTenantGroupName(renameGroupName)
      === normalizeTenantGroupName(selectedGroupForRenameCurrent.name);
  }, [renameGroupName, selectedGroupForRenameCurrent]);

  const membersSectionToggleLabel = translate(
    isMembersSectionExpanded
      ? "collapse_members_section"
      : "expand_members_section",
    isMembersSectionExpanded ? "Collapse members" : "Expand members",
  );

  const groupsSectionToggleLabel = translate(
    isGroupsSectionExpanded
      ? "collapse_groups_section"
      : "expand_groups_section",
    isGroupsSectionExpanded ? "Collapse groups" : "Expand groups",
  );

  const isInitialLoading = (
    isLoadingMembers
    && members.length === 0
    && isLoadingGroups
    && groups.length === 0
  );

  const handleOpenAddMemberDialog = () => {
    setMemberForm(emptyAddMemberForm());
    setAddMemberErrorMessage("");
    setAvailableUserSearch("");
    setAddMemberGroupSearch("");
    resetAvailableUserPagination();
    setAvailableUsersErrorMessage("");
    setIsAddMemberDialogOpen(true);
    void loadAllTenantGroups();
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
    void loadAllTenantGroups();
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

  const handleOpenRenameGroupDialog = (group: TenantGroup) => {
    setSelectedGroupForRename(group);
    setRenameGroupName(group.name);
    setRenameGroupErrorMessage("");
    setIsRenameGroupNameTouched(false);
    void loadAllTenantGroups();
  };

  const handleCloseRenameGroupDialog = () => {
    if (isSubmittingGroupRename) {
      return;
    }
    setSelectedGroupForRename(null);
    setRenameGroupName("");
    setRenameGroupErrorMessage("");
    setIsRenameGroupNameTouched(false);
  };

  const handleOpenMemberGroupsDialog = (member: TenantMember) => {
    setSelectedMemberForGroupManagement(member);
    void loadAllTenantGroups();
  };

  const handleCloseMemberGroupsDialog = () => {
    setSelectedMemberForGroupManagement(null);
  };

  const handleOpenGroupRolesDialog = (group: TenantGroup) => {
    setSelectedGroupForRoleManagement(group);
  };

  const handleCloseGroupRolesDialog = () => {
    setSelectedGroupForRoleManagement(null);
  };

  const handleOpenRemoveMemberDialog = (member: TenantMember) => {
    setMemberPendingRemoval(member);
  };

  const handleCloseRemoveMemberDialog = () => {
    if (memberRemovalUsername) {
      return;
    }
    setMemberPendingRemoval(null);
  };

  const handleOpenRemoveGroupDialog = (group: TenantGroup) => {
    setGroupPendingRemoval(group);
  };

  const handleCloseRemoveGroupDialog = () => {
    if (groupRemovalName) {
      return;
    }
    setGroupPendingRemoval(null);
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

  const handleRenameTenantGroup = async () => {
    if (!tenant || !selectedGroupForRenameCurrent) {
      return;
    }
    if (renameGroupValidationMessage || isRenameGroupUnchanged) {
      setIsRenameGroupNameTouched(true);
      return;
    }

    setIsSubmittingGroupRename(true);
    setRenameGroupErrorMessage("");
    try {
      await TenantService.renameTenantGroup(
        tenant.id,
        selectedGroupForRenameCurrent.name,
        {
          name: normalizeTenantGroupName(renameGroupName),
        },
      );
      handleCloseRenameGroupDialog();
      await refreshTenantAccessData();
    } catch (error: any) {
      setRenameGroupErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_rename_tenant_group",
            "Failed to rename tenant group.",
          ),
      );
    } finally {
      setIsSubmittingGroupRename(false);
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

  const handleRemoveTenantMember = async () => {
    if (!tenant || !memberPendingRemoval) {
      return;
    }

    setMemberRemovalUsername(memberPendingRemoval.username);
    setErrorMessage("");

    try {
      await TenantService.removeTenantMember(tenant.id, memberPendingRemoval.username);

      if (selectedMemberForGroupManagement?.username === memberPendingRemoval.username) {
        setSelectedMemberForGroupManagement(null);
      }
      setMemberPendingRemoval(null);
      await refreshTenantAccessData();
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_remove_tenant_member",
            "Failed to remove tenant member.",
          ),
      );
    } finally {
      setMemberRemovalUsername(null);
    }
  };

  const handleRemoveTenantGroup = async () => {
    if (!tenant || !groupPendingRemoval) {
      return;
    }

    setGroupRemovalName(groupPendingRemoval.name);
    setErrorMessage("");

    try {
      await TenantService.deleteTenantGroup(tenant.id, groupPendingRemoval.name);
      if (selectedGroupForRoleManagement?.id === groupPendingRemoval.id) {
        setSelectedGroupForRoleManagement(null);
      }
      setGroupPendingRemoval(null);
      await refreshTenantAccessData();
    } catch (error: any) {
      setErrorMessage(
        getErrorMessage(error)
          || translate(
            "failed_to_remove_tenant_group",
            "Failed to remove tenant group.",
          ),
      );
    } finally {
      setGroupRemovalName(null);
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
            "Add existing users as members and manage groups and roles associated with this tenant.",
          )}
        </Typography>
      )}

      {errorMessage && <Alert severity="error">{errorMessage}</Alert>}

      <Paper variant="outlined">
        {isInitialLoading ? (
          <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <Stack spacing={3} sx={{ p: 2 }}>
            <Box sx={SECTION_PANEL_SX}>
              <Box
                data-testid="tenant-members-section-header"
                sx={{
                  ...SECTION_HEADER_SX,
                  borderBottom: isMembersSectionExpanded ? "1px solid" : "none",
                  borderBottomColor: SECTION_PANEL_BORDER_COLOR,
                }}
              >
                <ButtonBase
                  onClick={toggleMembersSection}
                  data-testid="tenant-members-section-toggle"
                  aria-expanded={isMembersSectionExpanded}
                  aria-label={membersSectionToggleLabel}
                  sx={SECTION_HEADER_TOGGLE_SX}
                >
                  <Typography variant="subtitle1" fontWeight={600}>
                    {translate("members", "Members")}
                  </Typography>
                </ButtonBase>
                <IconButton
                  onClick={toggleMembersSection}
                  aria-label={membersSectionToggleLabel}
                  size="small"
                >
                  {isMembersSectionExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
              <Collapse in={isMembersSectionExpanded} unmountOnExit>
                <Box sx={SECTION_CONTENT_SX}>
                  <Box
                    data-testid="tenant-members-toolbar"
                    sx={{ ...SECTION_TOOLBAR_SX, mb: 1.5 }}
                  >
                    <TextField
                      size="small"
                      value={memberSearchQuery}
                      onChange={(event) => setMemberSearchQuery(event.target.value)}
                      placeholder={translate(
                        "search_organization_members",
                        "Search tenant members...",
                      )}
                      sx={{ flex: "1 1 280px", maxWidth: 360 }}
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
                    <Button
                      variant="contained"
                      startIcon={<PersonAddAlt1Icon />}
                      onClick={handleOpenAddMemberDialog}
                      disabled={!tenant}
                      data-testid="tenant-member-add-button"
                    >
                      {translate("add_tenant_user", "Add Member")}
                    </Button>
                  </Box>
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
                              <TableCell>
                                {translate("effective_roles", "Effective Roles")}
                              </TableCell>
                              <TableCell>{translate("groups", "Groups")}</TableCell>
                              <TableCell
                                align="center"
                                sx={{
                                  width: MEMBER_ACTIONS_CELL_WIDTH,
                                  minWidth: MEMBER_ACTIONS_CELL_WIDTH,
                                }}
                              >
                                {translate("action", "Action")}
                              </TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {members.map((member) => {
                              const memberGroups = member.groups ?? [];
                              const removeMemberDisabled = memberRemovalUsername !== null;
                              return (
                                <TableRow key={member.id || member.username} hover>
                                  <TableCell>{member.username}</TableCell>
                                  <TableCell>{member.display_name || "-"}</TableCell>
                                  <TableCell>{member.email || "-"}</TableCell>
                                  <TableCell sx={{ maxWidth: MEMBER_EFFECTIVE_ROLES_CELL_MAX_WIDTH }}>
                                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                      {member.roles.length > 0 ? (
                                        member.roles.map((roleName) => (
                                          <Chip
                                            key={`${member.username}:role:${roleName}`}
                                            size="small"
                                            label={roleLabel(roleName)}
                                            variant="outlined"
                                            data-testid={`tenant-member-role-chip-${member.username}-${roleName}`}
                                          />
                                        ))
                                      ) : (
                                        <Typography color="text.secondary">
                                          {translate(
                                            "no_effective_roles_assigned",
                                            "No effective roles",
                                          )}
                                        </Typography>
                                      )}
                                    </Stack>
                                  </TableCell>
                                  <TableCell sx={{ maxWidth: MEMBER_GROUPS_CELL_MAX_WIDTH }}>
                                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                      {memberGroups.length > 0 ? (
                                        memberGroups.map((group) => (
                                          <Chip
                                            key={`${member.username}:${group.id}`}
                                            size="small"
                                            label={group.name}
                                            variant="outlined"
                                            data-testid={`tenant-member-group-chip-${member.username}-${group.name}`}
                                          />
                                        ))
                                      ) : (
                                        <Typography color="text.secondary">
                                          {translate("no_groups_assigned", "No groups")}
                                        </Typography>
                                      )}
                                    </Stack>
                                  </TableCell>
                                  <TableCell
                                    align="center"
                                    sx={{
                                      width: MEMBER_ACTIONS_CELL_WIDTH,
                                      minWidth: MEMBER_ACTIONS_CELL_WIDTH,
                                    }}
                                  >
                                    <Stack
                                      direction="row"
                                      spacing={0.5}
                                      justifyContent="center"
                                    >
                                      <Tooltip
                                        title={translate(
                                          "manage_member_groups",
                                          "Manage Member Groups",
                                        )}
                                      >
                                        <span>
                                          <IconButton
                                            size="small"
                                            onClick={() => handleOpenMemberGroupsDialog(member)}
                                            data-testid={`tenant-member-manage-groups-button-${member.username}`}
                                          >
                                            <ManageAccountsIcon fontSize="small" />
                                          </IconButton>
                                        </span>
                                      </Tooltip>
                                      <Tooltip
                                        title={translate(
                                          "remove_tenant_member",
                                          "Remove Member",
                                        )}
                                      >
                                        <span>
                                          <IconButton
                                            size="small"
                                            color="error"
                                            disabled={removeMemberDisabled}
                                            onClick={() => handleOpenRemoveMemberDialog(member)}
                                            data-testid={`tenant-member-remove-button-${member.username}`}
                                          >
                                            <DeleteOutlineIcon fontSize="small" />
                                          </IconButton>
                                        </span>
                                      </Tooltip>
                                    </Stack>
                                  </TableCell>
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
              <Box
                data-testid="tenant-groups-section-header"
                sx={{
                  ...SECTION_HEADER_SX,
                  borderBottom: isGroupsSectionExpanded ? "1px solid" : "none",
                  borderBottomColor: SECTION_PANEL_BORDER_COLOR,
                }}
              >
                <ButtonBase
                  onClick={toggleGroupsSection}
                  data-testid="tenant-groups-section-toggle"
                  aria-expanded={isGroupsSectionExpanded}
                  aria-label={groupsSectionToggleLabel}
                  sx={SECTION_HEADER_TOGGLE_SX}
                >
                  <Typography variant="subtitle1" fontWeight={600}>
                    {translate("groups", "Groups")}
                  </Typography>
                </ButtonBase>
                <IconButton
                  onClick={toggleGroupsSection}
                  aria-label={groupsSectionToggleLabel}
                  size="small"
                >
                  {isGroupsSectionExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
              <Collapse in={isGroupsSectionExpanded} unmountOnExit>
                <Box sx={SECTION_CONTENT_SX}>
                  <Box
                    data-testid="tenant-groups-toolbar"
                    sx={{ ...SECTION_TOOLBAR_SX, mb: 1.5 }}
                  >
                    <TextField
                      size="small"
                      value={groupSearchQuery}
                      onChange={(event) => setGroupSearchQuery(event.target.value)}
                      placeholder={translate(
                        "search_groups_or_roles",
                        "Search groups or roles...",
                      )}
                      sx={{ flex: "1 1 280px", maxWidth: 360 }}
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
                    <Button
                      variant="contained"
                      startIcon={<GroupAddIcon />}
                      onClick={handleOpenCreateGroupDialog}
                      disabled={!tenant}
                      data-testid="tenant-group-add-button"
                    >
                      {translate("create_group", "Create Group")}
                    </Button>
                  </Box>
                  {isLoadingGroups ? (
                    <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
                      <CircularProgress />
                    </Box>
                  ) : groups.length === 0 ? (
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
                    <Stack spacing={1.5}>
                      <TableContainer
                        sx={{
                          maxHeight: 360,
                          borderRadius: 1,
                          backgroundColor: "background.paper",
                        }}
                        data-testid="tenant-group-table-container"
                      >
                        <Table stickyHeader size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>{translate("group", "Group")}</TableCell>
                              <TableCell>
                                {translate("granted_roles", "Granted Roles")}
                              </TableCell>
                              <TableCell>{translate("members", "Members")}</TableCell>
                              <TableCell
                                align="center"
                                sx={{
                                  width: GROUP_ACTIONS_CELL_WIDTH,
                                  minWidth: GROUP_ACTIONS_CELL_WIDTH,
                                }}
                              >
                                {translate("action", "Action")}
                              </TableCell>
                            </TableRow>
                          </TableHead>
                        <TableBody>
                          {groups.map((group) => (
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
                              <TableCell sx={{ maxWidth: GROUP_GRANTED_ROLES_CELL_MAX_WIDTH }}>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                  {group.mapped_roles.length > 0 ? (
                                    group.mapped_roles.map((roleName) => (
                                      <Chip
                                        key={`${group.id}:${roleName}`}
                                        size="small"
                                        label={roleLabel(roleName)}
                                        variant="outlined"
                                        data-testid={`tenant-group-role-chip-${group.id}-${roleName}`}
                                      />
                                    ))
                                  ) : (
                                    <Typography color="text.secondary">
                                      {translate(
                                        "no_granted_roles_assigned",
                                        "No granted roles",
                                      )}
                                    </Typography>
                                  )}
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
                              <TableCell
                                align="center"
                                sx={{
                                  width: GROUP_ACTIONS_CELL_WIDTH,
                                  minWidth: GROUP_ACTIONS_CELL_WIDTH,
                                }}
                              >
                                <Stack
                                  direction="row"
                                  spacing={0.5}
                                  justifyContent="center"
                                >
                                  <Tooltip
                                    title={translate(
                                      "rename_tenant_group",
                                      "Rename Group",
                                    )}
                                  >
                                    <span>
                                      <IconButton
                                        size="small"
                                        onClick={() => handleOpenRenameGroupDialog(group)}
                                        data-testid={`tenant-group-rename-button-${group.name}`}
                                      >
                                        <EditIcon fontSize="small" />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                  <Tooltip
                                    title={translate(
                                      "manage_granted_roles",
                                      "Manage Granted Roles",
                                    )}
                                  >
                                    <span>
                                      <IconButton
                                        size="small"
                                        onClick={() => handleOpenGroupRolesDialog(group)}
                                        data-testid={`tenant-group-manage-roles-button-${group.name}`}
                                      >
                                        <ManageAccountsIcon fontSize="small" />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                  <Tooltip
                                    title={translate(
                                      "remove_tenant_group",
                                      "Remove Group",
                                    )}
                                  >
                                    <span>
                                      <IconButton
                                        size="small"
                                        color="error"
                                        onClick={() => handleOpenRemoveGroupDialog(group)}
                                        disabled={Boolean(groupRemovalName)}
                                        data-testid={`tenant-group-remove-button-${group.name}`}
                                      >
                                        <DeleteOutlineIcon fontSize="small" />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                </Stack>
                              </TableCell>
                            </TableRow>
                          ))}
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
                          data-testid="tenant-group-page-indicator"
                        >
                          {translate(
                            "tenant_groups_page_indicator",
                            `Page ${currentGroupPage + 1}`,
                            { page: currentGroupPage + 1 },
                          )}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleGroupPageChange(currentGroupPage - 1)}
                            disabled={!canGoToPreviousGroupPage || isLoadingGroups}
                            data-testid="tenant-group-previous-page-button"
                          >
                            {translate("previous_page", "Previous")}
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleGroupPageChange(currentGroupPage + 1)}
                            disabled={!canGoToNextGroupPage || isLoadingGroups}
                            data-testid="tenant-group-next-page-button"
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
        open={Boolean(selectedMemberForGroupManagement)}
        onClose={handleCloseMemberGroupsDialog}
        fullWidth
        maxWidth="sm"
        data-testid="tenant-member-groups-dialog"
      >
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("manage_member_groups", "Manage Member Groups")}
          {selectedMemberForGroupManagementCurrent
            ? `: ${selectedMemberForGroupManagementCurrent.username}`
            : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "manage_member_groups_description",
                "Add or remove this member from tenant groups.",
              )}
            </Typography>
            {isLoadingAllGroups ? (
              <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                <CircularProgress size={24} />
              </Box>
            ) : allGroups.length === 0 ? (
              <Typography color="text.secondary">
                {translate("no_tenant_groups_found", "No tenant groups found.")}
              </Typography>
            ) : (
              <Stack spacing={1}>
                {allGroups.map((group) => {
                  const mutationKey = selectedMemberForGroupManagementCurrent
                    ? `${selectedMemberForGroupManagementCurrent.username}:${group.name}`
                    : "";
                  const checked = selectedMemberForGroupManagementCurrent
                    ? (
                        selectedMemberForGroupManagementCurrent.groups ?? []
                      ).some((memberGroup) => memberGroup.name === group.name)
                    : false;

                  return (
                    <Box
                      key={`tenant-member-groups-dialog-row-${group.id}`}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 2,
                        p: 1.5,
                        border: "1px solid",
                        borderColor: "divider",
                        borderRadius: 1,
                      }}
                    >
                      <Box sx={{ minWidth: 0, flex: "1 1 auto" }}>
                        <Tooltip title={group.name}>
                          <Typography sx={truncatedValueSx}>{group.name}</Typography>
                        </Tooltip>
                        {group.mapped_roles.length > 0 ? (
                          <Typography variant="body2" color="text.secondary">
                            {group.mapped_roles.map((roleName) => roleLabel(roleName)).join(", ")}
                          </Typography>
                        ) : null}
                      </Box>
                      <Checkbox
                        checked={checked}
                        disabled={
                          groupMutationKey === mutationKey
                          || !selectedMemberForGroupManagementCurrent
                        }
                        onChange={(event) => {
                          if (!selectedMemberForGroupManagementCurrent) {
                            return;
                          }
                          void handleToggleGroupMembership(
                            selectedMemberForGroupManagementCurrent,
                            group,
                            event.target.checked,
                          );
                        }}
                        inputProps={{
                          ...testIdInputProps(
                            `tenant-member-groups-dialog-checkbox-${selectedMemberForGroupManagementCurrent?.username ?? "unknown"}-${group.name}`,
                          ),
                        }}
                      />
                    </Box>
                  );
                })}
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseMemberGroupsDialog}>
            {translate("close", "Close")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(memberPendingRemoval)}
        onClose={handleCloseRemoveMemberDialog}
        fullWidth
        maxWidth="xs"
        data-testid="tenant-member-remove-dialog"
      >
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("remove_tenant_member", "Remove Member")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "remove_tenant_member_confirmation",
                "Remove this member from the tenant?",
              )}
            </Typography>
            {memberPendingRemoval ? (
              <Typography fontWeight={600}>{memberPendingRemoval.username}</Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseRemoveMemberDialog} disabled={Boolean(memberRemovalUsername)}>
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => void handleRemoveTenantMember()}
            disabled={Boolean(memberRemovalUsername)}
            data-testid="tenant-member-remove-confirm-button"
          >
            {memberRemovalUsername
              ? translate("processing", "Processing...")
              : translate("remove", "Remove")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(selectedGroupForRename)}
        onClose={handleCloseRenameGroupDialog}
        fullWidth
        maxWidth="sm"
        data-testid="tenant-group-rename-dialog"
      >
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("rename_tenant_group", "Rename Group")}
          {selectedGroupForRenameCurrent
            ? `: ${selectedGroupForRenameCurrent.name}`
            : selectedGroupForRename
              ? `: ${selectedGroupForRename.name}`
              : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "rename_tenant_group_description",
                "Change this group's name while keeping its members and granted roles.",
              )}
            </Typography>
            {renameGroupErrorMessage && (
              <Alert severity="error">{renameGroupErrorMessage}</Alert>
            )}
            <TextField
              label={translate("group_name", "Group Name")}
              value={renameGroupName}
              onChange={(event) => {
                setRenameGroupName(event.target.value);
                setIsRenameGroupNameTouched(true);
                if (renameGroupErrorMessage) {
                  setRenameGroupErrorMessage("");
                }
              }}
              onBlur={() => {
                setIsRenameGroupNameTouched(true);
                setRenameGroupName((current) => normalizeTenantGroupName(current));
              }}
              error={isRenameGroupNameTouched && Boolean(renameGroupValidationMessage)}
              helperText={
                isRenameGroupNameTouched && renameGroupValidationMessage
                  ? renameGroupValidationMessage
                  : translate(
                      "tenant_group_name_helper",
                      `Up to ${TENANT_GROUP_NAME_MAX_LENGTH} characters. Letters, numbers, spaces, hyphens, and underscores only.`,
                    )
              }
              inputProps={{
                maxLength: TENANT_GROUP_NAME_MAX_LENGTH,
                ...testIdInputProps("tenant-group-rename-input"),
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={handleCloseRenameGroupDialog}
            disabled={isSubmittingGroupRename}
          >
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleRenameTenantGroup()}
            disabled={
              isSubmittingGroupRename
              || isLoadingAllGroups
              || !renameGroupName.trim()
              || Boolean(renameGroupValidationMessage)
              || isRenameGroupUnchanged
            }
            data-testid="tenant-group-rename-submit-button"
          >
            {isSubmittingGroupRename
              ? translate("processing", "Processing...")
              : translate("save", "Save")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(selectedGroupForRoleManagement)}
        onClose={handleCloseGroupRolesDialog}
        fullWidth
        maxWidth="sm"
        data-testid="tenant-group-roles-dialog"
      >
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("manage_granted_roles", "Manage Granted Roles")}
          {selectedGroupForRoleManagementCurrent
            ? `: ${selectedGroupForRoleManagementCurrent.name}`
            : selectedGroupForRoleManagement
              ? `: ${selectedGroupForRoleManagement.name}`
              : ""}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "manage_granted_roles_description",
                "Grant or revoke tenant roles for this group.",
              )}
            </Typography>
            <Stack spacing={1}>
              {TENANT_MEMBER_ROLES.map((roleName) => {
                const currentGroup = selectedGroupForRoleManagementCurrent;
                const mutationKey = currentGroup ? `${currentGroup.name}:${roleName}` : "";
                const checked = currentGroup?.mapped_roles.includes(roleName) ?? false;
                return (
                  <Box
                    key={`tenant-group-roles-dialog-row-${roleName}`}
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 2,
                      p: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1,
                    }}
                  >
                    <Typography>{roleLabel(roleName)}</Typography>
                    <Checkbox
                      checked={checked}
                      disabled={!currentGroup || groupRoleMutationKey === mutationKey}
                      onChange={(event) => {
                        if (!currentGroup) {
                          return;
                        }
                        void handleToggleGroupRole(
                          currentGroup,
                          roleName,
                          event.target.checked,
                        );
                      }}
                      inputProps={{
                        ...testIdInputProps(
                          `tenant-group-role-checkbox-${selectedGroupForRoleManagement?.name ?? "unknown"}-${roleName}`,
                        ),
                      }}
                    />
                  </Box>
                );
              })}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseGroupRolesDialog}>
            {translate("close", "Close")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(groupPendingRemoval)}
        onClose={handleCloseRemoveGroupDialog}
        fullWidth
        maxWidth="xs"
        data-testid="tenant-group-remove-dialog"
      >
        <DialogTitle sx={DIALOG_TITLE_SX}>
          {translate("remove_tenant_group", "Remove Group")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {translate(
                "remove_tenant_group_confirmation",
                "Remove this group from the tenant? Members will remain in the tenant, but any roles granted through this group will be removed.",
              )}
            </Typography>
            {groupPendingRemoval ? (
              <Typography fontWeight={600}>{groupPendingRemoval.name}</Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseRemoveGroupDialog} disabled={Boolean(groupRemovalName)}>
            {translate("cancel", "Cancel")}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => void handleRemoveTenantGroup()}
            disabled={Boolean(groupRemovalName)}
            data-testid="tenant-group-remove-confirm-button"
          >
            {groupRemovalName
              ? translate("processing", "Processing...")
              : translate("remove", "Remove")}
          </Button>
        </DialogActions>
      </Dialog>

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
                {isLoadingAllGroups ? (
                  <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                    <CircularProgress size={24} />
                  </Box>
                ) : filteredAddMemberGroups.length === 0 ? (
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
              || isLoadingAllGroups
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
