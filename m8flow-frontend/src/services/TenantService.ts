import HttpService from "@spiffworkflow-frontend/services/HttpService";

const BASE_PATH = "/v1.0/m8flow";
const MAX_TENANT_GROUP_PAGE_REQUESTS = 1000;

// Shared type definitions
export type TenantStatus = "ACTIVE" | "INACTIVE" | "DELETED";
export type EditableTenantStatus = Exclude<TenantStatus, "DELETED">;

export interface Tenant {
    id: string;
    name: string;
    slug: string;
    status: TenantStatus;
    createdBy: string;
    modifiedBy: string;
    createdAtInSeconds: number;
    updatedAtInSeconds: number;
}

export type TenantMemberRole =
    | "tenant-admin"
    | "editor"
    | "integrator"
    | "reviewer"
    | "submitter"
    | "viewer";

export const TENANT_MEMBER_ROLES: TenantMemberRole[] = [
    "tenant-admin",
    "editor",
    "integrator",
    "reviewer",
    "submitter",
    "viewer",
];

export const TENANT_GROUP_NAME_MAX_LENGTH = 64;
const TENANT_GROUP_NAME_ALLOWED_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$/;

export interface TenantMember {
    id: string;
    username: string;
    email: string | null;
    display_name: string | null;
    roles: TenantMemberRole[];
    groups: TenantMemberGroup[];
}

export interface TenantMemberGroup {
    id: string;
    name: string;
}

export interface TenantGroupMember {
    id: string;
    username: string;
    email: string | null;
    display_name: string | null;
}

export interface TenantAvailableUser {
    id: string;
    username: string;
    email: string | null;
    display_name: string | null;
}

export interface TenantGroup {
    id: string;
    name: string;
    path: string | null;
    mapped_roles: TenantMemberRole[];
    member_count: number;
    members: TenantGroupMember[];
}

export interface AddTenantMemberRequest {
    username: string;
    group_names?: string[];
}

export interface CreateTenantGroupRequest {
    name: string;
}

export interface RenameTenantGroupRequest {
    name: string;
}

export const normalizeTenantGroupName = (name: string): string =>
    name.trim().replace(/\s+/g, " ");

export const validateTenantGroupName = (name: string): string | null => {
    const normalizedName = normalizeTenantGroupName(name);

    if (!normalizedName) {
        return "Group name cannot be empty";
    }

    if (normalizedName.length > TENANT_GROUP_NAME_MAX_LENGTH) {
        return `Group name must be ${TENANT_GROUP_NAME_MAX_LENGTH} characters or fewer`;
    }

    if (!TENANT_GROUP_NAME_ALLOWED_PATTERN.test(normalizedName)) {
        return "Group name can only contain letters, numbers, spaces, hyphens, and underscores, and must start and end with a letter or number";
    }

    return null;
};

export interface UpdateTenantRequest {
    name?: string;
    status?: TenantStatus;
}

export interface CreateTenantRequest {
    slug: string;
    name: string;
}

export interface CreateTenantResponse {
    id: string;
    organization_id: string;
    alias: string;
    name: string;
    realm?: string;
    displayName?: string;
    keycloak_realm_id?: string;
}

export interface TenantOrganizationMembership {
    alias: string;
    id: string | null;
    name: string | null;
}

interface TenantMembersResponse {
    tenant_id: string;
    search: string;
    offset?: number;
    limit?: number;
    has_more?: boolean;
    members: TenantMember[];
}

export interface TenantMembersPage {
    tenant_id: string;
    search: string;
    offset: number;
    limit: number;
    has_more: boolean;
    members: TenantMember[];
}

export interface TenantMemberPageRequest {
    search?: string;
    offset?: number;
    limit?: number;
}

interface TenantGroupsResponse {
    tenant_id: string;
    search: string;
    offset?: number;
    limit?: number;
    has_more?: boolean;
    groups: TenantGroup[];
}

export interface TenantGroupsPage {
    tenant_id: string;
    search: string;
    offset: number;
    limit: number;
    has_more: boolean;
    groups: TenantGroup[];
}

export interface TenantGroupPageRequest {
    search?: string;
    offset?: number;
    limit?: number;
}

interface TenantGroupCreateResponse {
    tenant_id: string;
    group: TenantGroup;
}

interface TenantGroupUpdateResponse {
    tenant_id: string;
    previous_group_name: string;
    group: TenantGroup;
}

interface TenantGroupDeleteResponse {
    tenant_id: string;
    group_name: string;
}

interface TenantAvailableUsersResponse {
    tenant_id: string;
    search: string;
    offset?: number;
    limit?: number;
    has_more?: boolean;
    users: TenantAvailableUser[];
}

export interface TenantAvailableUsersPage {
    tenant_id: string;
    search: string;
    offset: number;
    limit: number;
    has_more: boolean;
    users: TenantAvailableUser[];
}

export interface TenantAvailableUserPageRequest {
    search?: string;
    offset?: number;
    limit?: number;
}

interface TenantOrganizationMembershipsResponse {
    organizations: TenantOrganizationMembership[];
}

interface TenantMemberCreateResponse {
    tenant_id: string;
    group_names: string[];
    member: TenantMember;
}

interface TenantGroupMembershipMutationResponse {
    tenant_id: string;
    group_name: string;
    username: string;
    member: TenantMember;
}

interface TenantGroupRoleMutationResponse {
    tenant_id: string;
    group_name: string;
    role_name: TenantMemberRole;
    group: TenantGroup;
}

const normalizeTenantMember = (member: TenantMember): TenantMember => ({
    ...member,
    groups: member.groups ?? [],
});

const normalizeTenantMembers = (members: TenantMember[] | undefined): TenantMember[] =>
    (members ?? []).map(normalizeTenantMember);

const TenantService = {
    /**
     * Get all tenants
     */
    getAllTenants: (): Promise<Tenant[]> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants`,
                httpMethod: "GET",
                successCallback: resolve,
                failureCallback: reject,
            });
        });
    },

    /**
     * Resolve the current user's organization memberships to display names.
     */
    getCurrentUserOrganizationMemberships: (): Promise<TenantOrganizationMembership[]> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/organization-memberships`,
                httpMethod: "GET",
                successCallback: (response: TenantOrganizationMembershipsResponse) =>
                    resolve(response.organizations ?? []),
                failureCallback: reject,
            });
        });
    },

    /**
     * Create a tenant organization in the shared realm
     */
    createTenant: (data: CreateTenantRequest): Promise<CreateTenantResponse> => {
        const tenantAlias = data.slug.trim();
        const tenantName = data.name.trim();

        if (!tenantAlias) {
            return Promise.reject(new Error("Tenant slug cannot be empty"));
        }
        if (!tenantName) {
            return Promise.reject(new Error("Tenant display name cannot be empty"));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenant-realms`,
                httpMethod: "POST",
                postBody: {
                    slug: tenantAlias,
                    name: tenantName,
                },
                successCallback: resolve,
                failureCallback: reject,
            });
        });
    },

    /**
     * Update a tenant
     */
    updateTenant: (id: string, data: UpdateTenantRequest): Promise<Tenant> => {
        // Validate that name is not empty if provided
        if (data.name !== undefined && !data.name.trim()) {
            return Promise.reject(new Error("Tenant name cannot be empty"));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${id}`,
                httpMethod: "PUT",
                postBody: data,
                successCallback: resolve,
                failureCallback: reject,
            });
        });
    },

    /**
     * Soft delete a tenant
     */
    deleteTenant: (id: string): Promise<void> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${id}`,
                httpMethod: "DELETE",
                successCallback: resolve,
                failureCallback: reject,
            });
        });
    },

    /**
     * List tenant organization members and their tenant-local roles
     */
    getTenantMembers: (tenantId: string, search = ""): Promise<TenantMember[]> => {
        return TenantService.getTenantMembersPage(tenantId, {
            search,
            offset: 0,
            limit: 100,
        }).then((response) => response.members);
    },

    /**
     * List one page of tenant organization members and their tenant-local roles
     */
    getTenantMembersPage: (
        tenantId: string,
        options: TenantMemberPageRequest = {},
    ): Promise<TenantMembersPage> => {
        const searchParams = new URLSearchParams();
        const normalizedSearch = options.search?.trim() ?? "";
        const offset = Math.max(0, options.offset ?? 0);
        const limit = Math.max(1, options.limit ?? 10);
        if (normalizedSearch) {
            searchParams.set("search", normalizedSearch);
        }
        searchParams.set("offset", `${offset}`);
        searchParams.set("limit", `${limit}`);
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/members${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantMembersResponse) =>
                    resolve({
                        tenant_id: response.tenant_id,
                        search: response.search ?? normalizedSearch,
                        offset: response.offset ?? offset,
                        limit: response.limit ?? limit,
                        has_more: Boolean(response.has_more),
                        members: normalizeTenantMembers(response.members),
                    }),
                failureCallback: reject,
            });
        });
    },

    /**
     * List existing users that are not yet members of this tenant.
     */
    getAvailableTenantUsers: (tenantId: string, search = ""): Promise<TenantAvailableUser[]> => {
        return TenantService.getAvailableTenantUsersPage(tenantId, {
            search,
            offset: 0,
            limit: 100,
        }).then((response) => response.users);
    },

    /**
     * List one page of existing users that are not yet members of this tenant.
     */
    getAvailableTenantUsersPage: (
        tenantId: string,
        options: TenantAvailableUserPageRequest = {},
    ): Promise<TenantAvailableUsersPage> => {
        const searchParams = new URLSearchParams();
        const normalizedSearch = options.search?.trim() ?? "";
        const offset = Math.max(0, options.offset ?? 0);
        const limit = Math.max(1, options.limit ?? 10);
        if (normalizedSearch) {
            searchParams.set("search", normalizedSearch);
        }
        searchParams.set("offset", `${offset}`);
        searchParams.set("limit", `${limit}`);
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/available-users${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantAvailableUsersResponse) =>
                    resolve({
                        tenant_id: response.tenant_id,
                        search: response.search ?? normalizedSearch,
                        offset: response.offset ?? offset,
                        limit: response.limit ?? limit,
                        has_more: Boolean(response.has_more),
                        users: response.users ?? [],
                    }),
                failureCallback: reject,
            });
        });
    },

    /**
     * Add one existing user to a tenant organization.
     */
    addTenantMember: (
        tenantId: string,
        data: AddTenantMemberRequest,
    ): Promise<TenantMember> => {
        const username = data.username?.trim();
        if (!username) {
            return Promise.reject(new Error("Username cannot be empty"));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/members`,
                httpMethod: "POST",
                postBody: {
                    username,
                    group_names: data.group_names ?? [],
                },
                successCallback: (response: TenantMemberCreateResponse) =>
                    resolve(normalizeTenantMember(response.member)),
                failureCallback: reject,
            });
        });
    },

    /**
     * List tenant organization groups and their members
     */
    getTenantGroups: async (tenantId: string, search = ""): Promise<TenantGroup[]> => {
        const groups: TenantGroup[] = [];
        const limit = 100;
        let offset = 0;
        let pageRequests = 0;
        let didComplete = false;

        while (pageRequests < MAX_TENANT_GROUP_PAGE_REQUESTS) {
            pageRequests += 1;
            const response = await TenantService.getTenantGroupsPage(tenantId, {
                search,
                offset,
                limit,
            });
            groups.push(...response.groups);
            if (!response.has_more || response.groups.length === 0) {
                didComplete = true;
                break;
            }

            if (response.offset < offset) {
                throw new Error("Tenant group pagination returned a stale page.");
            }

            const nextOffset = offset + response.groups.length;
            if (nextOffset <= offset) {
                throw new Error("Tenant group pagination did not advance.");
            }

            offset = nextOffset;
        }

        if (!didComplete) {
            throw new Error("Tenant group pagination exceeded the maximum number of pages.");
        }

        return groups;
    },

    /**
     * List one page of tenant organization groups and their members
     */
    getTenantGroupsPage: (
        tenantId: string,
        options: TenantGroupPageRequest = {},
    ): Promise<TenantGroupsPage> => {
        const searchParams = new URLSearchParams();
        const normalizedSearch = options.search?.trim() ?? "";
        const offset = Math.max(0, options.offset ?? 0);
        const limit = Math.max(1, options.limit ?? 10);
        if (normalizedSearch) {
            searchParams.set("search", normalizedSearch);
        }
        searchParams.set("offset", `${offset}`);
        searchParams.set("limit", `${limit}`);
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantGroupsResponse) =>
                    resolve({
                        tenant_id: response.tenant_id,
                        search: response.search ?? normalizedSearch,
                        offset: response.offset ?? offset,
                        limit: response.limit ?? limit,
                        has_more: Boolean(response.has_more),
                        groups: response.groups ?? [],
                    }),
                failureCallback: reject,
            });
        });
    },

    /**
     * Create one tenant organization group.
     */
    createTenantGroup: (
        tenantId: string,
        data: CreateTenantGroupRequest,
    ): Promise<TenantGroup> => {
        const name = normalizeTenantGroupName(data.name ?? "");
        const validationMessage = validateTenantGroupName(name);
        if (validationMessage) {
            return Promise.reject(new Error(validationMessage));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups`,
                httpMethod: "POST",
                postBody: { name },
                successCallback: (response: TenantGroupCreateResponse) =>
                    resolve(response.group),
                failureCallback: reject,
            });
        });
    },

    /**
     * Rename one tenant organization group.
     */
    renameTenantGroup: (
        tenantId: string,
        currentGroupName: string,
        data: RenameTenantGroupRequest,
    ): Promise<TenantGroup> => {
        const name = normalizeTenantGroupName(data.name ?? "");
        const validationMessage = validateTenantGroupName(name);
        if (validationMessage) {
            return Promise.reject(new Error(validationMessage));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    currentGroupName,
                )}`,
                httpMethod: "PUT",
                postBody: { name },
                successCallback: (response: TenantGroupUpdateResponse) =>
                    resolve(response.group),
                failureCallback: reject,
            });
        });
    },

    /**
     * Delete one tenant organization group.
     */
    deleteTenantGroup: (tenantId: string, groupName: string): Promise<string> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    groupName,
                )}`,
                httpMethod: "DELETE",
                successCallback: (response: TenantGroupDeleteResponse) =>
                    resolve(response.group_name),
                failureCallback: reject,
            });
        });
    },

    /**
     * Assign one tenant member to one organization group.
     */
    addTenantMemberToGroup: (
        tenantId: string,
        username: string,
        groupName: string,
    ): Promise<TenantMember> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    groupName,
                )}/members/${encodeURIComponent(username)}`,
                httpMethod: "PUT",
                successCallback: (response: TenantGroupMembershipMutationResponse) =>
                    resolve(normalizeTenantMember(response.member)),
                failureCallback: reject,
            });
        });
    },

    /**
     * Remove one tenant member from one organization group.
     */
    removeTenantMemberFromGroup: (
        tenantId: string,
        username: string,
        groupName: string,
    ): Promise<TenantMember> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    groupName,
                )}/members/${encodeURIComponent(username)}`,
                httpMethod: "DELETE",
                successCallback: (response: TenantGroupMembershipMutationResponse) =>
                    resolve(normalizeTenantMember(response.member)),
                failureCallback: reject,
            });
        });
    },

    /**
     * Assign one tenant-scoped role to one organization group.
     */
    assignTenantGroupRole: (
        tenantId: string,
        groupName: string,
        roleName: TenantMemberRole,
    ): Promise<TenantGroup> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    groupName,
                )}/roles/${encodeURIComponent(roleName)}`,
                httpMethod: "PUT",
                successCallback: (response: TenantGroupRoleMutationResponse) =>
                    resolve(response.group),
                failureCallback: reject,
            });
        });
    },

    /**
     * Remove one tenant-scoped role from one organization group.
     */
    removeTenantGroupRole: (
        tenantId: string,
        groupName: string,
        roleName: TenantMemberRole,
    ): Promise<TenantGroup> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups/${encodeURIComponent(
                    groupName,
                )}/roles/${encodeURIComponent(roleName)}`,
                httpMethod: "DELETE",
                successCallback: (response: TenantGroupRoleMutationResponse) =>
                    resolve(response.group),
                failureCallback: reject,
            });
        });
    },

    /**
     * Assign one tenant-scoped role to one organization member
     */
    assignTenantMemberRole: (
        tenantId: string,
        username: string,
        roleName: TenantMemberRole,
    ): Promise<TenantMember> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/members/${encodeURIComponent(
                    username,
                )}/roles/${encodeURIComponent(roleName)}`,
                httpMethod: "PUT",
                successCallback: (response: { member: TenantMember }) =>
                    resolve(normalizeTenantMember(response.member)),
                failureCallback: reject,
            });
        });
    },

    /**
     * Remove one tenant-scoped role from one organization member
     */
    removeTenantMemberRole: (
        tenantId: string,
        username: string,
        roleName: TenantMemberRole,
    ): Promise<TenantMember> => {
        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/members/${encodeURIComponent(
                    username,
                )}/roles/${encodeURIComponent(roleName)}`,
                httpMethod: "DELETE",
                successCallback: (response: { member: TenantMember }) =>
                    resolve(normalizeTenantMember(response.member)),
                failureCallback: reject,
            });
        });
    },
};

export default TenantService;
