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

export interface UpdateTenantRequest {
    name?: string;
    status?: TenantStatus;
}

export interface CreateTenantRequest {
    realm_id: string;
    display_name: string;
}

export interface CreateTenantResponse {
    realm: string;
    displayName: string;
    keycloak_realm_id: string;
    id: string;
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
     * Create a tenant realm
     */
    createTenant: (data: CreateTenantRequest): Promise<CreateTenantResponse> => {
        const realmId = data.realm_id.trim();
        const displayName = data.display_name.trim();

        if (!realmId) {
            return Promise.reject(new Error("Tenant slug cannot be empty"));
        }
        if (!displayName) {
            return Promise.reject(new Error("Tenant display name cannot be empty"));
        }

        return new Promise((resolve, reject) => {
            HttpService.makeCallToBackend({
                path: `${BASE_PATH}/tenant-realms`,
                httpMethod: "POST",
                postBody: {
                    realm_id: realmId,
                    display_name: displayName,
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
};

export default TenantService;
