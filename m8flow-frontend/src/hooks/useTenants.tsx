import { useQuery } from "@tanstack/react-query";
import TenantService, { Tenant } from "../services/TenantService";

export const useTenants = () => {
  return useQuery<Tenant[], Error>({
    queryKey: ["tenants"],
    queryFn: () => TenantService.getAllTenants(),
  });
};
