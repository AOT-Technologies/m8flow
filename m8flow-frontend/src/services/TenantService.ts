import HttpService from "@spiffworkflow-frontend/services/HttpService";

const BASE_PATH = "/v1.0/m8flow";

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

export interface TenantMember {
    id: string;
    username: string;
    email: string | null;
    display_name: string | null;
    roles: TenantMemberRole[];
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

interface TenantMembersResponse {
    tenant_id: string;
    search: string;
    members: TenantMember[];
}

interface TenantGroupsResponse {
    tenant_id: string;
    search: string;
    groups: TenantGroup[];
}

interface TenantGroupCreateResponse {
    tenant_id: string;
    group: TenantGroup;
}

interface TenantAvailableUsersResponse {
    tenant_id: string;
    search: string;
    users: TenantAvailableUser[];
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
        const searchParams = new URLSearchParams();
        if (search.trim()) {
            searchParams.set("search", search.trim());
        }
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/members${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantMembersResponse) =>
                    resolve(response.members ?? []),
                failureCallback: reject,
            });
        });
    },

    /**
     * List existing users that are not yet members of this tenant.
     */
    getAvailableTenantUsers: (tenantId: string, search = ""): Promise<TenantAvailableUser[]> => {
        const searchParams = new URLSearchParams();
        if (search.trim()) {
            searchParams.set("search", search.trim());
        }
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/available-users${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantAvailableUsersResponse) =>
                    resolve(response.users ?? []),
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
                    resolve(response.member),
                failureCallback: reject,
            });
        });
    },

    /**
     * List tenant organization groups and their members
     */
    getTenantGroups: (tenantId: string, search = ""): Promise<TenantGroup[]> => {
        const searchParams = new URLSearchParams();
        if (search.trim()) {
            searchParams.set("search", search.trim());
        }
        const queryString = searchParams.toString();
        const path = `${BASE_PATH}/tenants/${encodeURIComponent(tenantId)}/groups${
            queryString ? `?${queryString}` : ""
        }`;

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path,
                httpMethod: "GET",
                successCallback: (response: TenantGroupsResponse) =>
                    resolve(response.groups ?? []),
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
        const name = data.name?.trim();
        if (!name) {
            return Promise.reject(new Error("Group name cannot be empty"));
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
                    resolve(response.member),
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
                    resolve(response.member),
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
                    resolve(response.member),
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
                    resolve(response.member),
                failureCallback: reject,
            });
        });
    },
};

export default TenantService;
