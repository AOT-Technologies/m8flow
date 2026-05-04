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
    | "viewer";

export interface TenantMember {
    id: string;
    username: string;
    email: string | null;
    display_name: string | null;
    roles: TenantMemberRole[];
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
