export function isTenantAdminGroup(groupIdentifier: string): boolean {
  return groupIdentifier === "tenant-admin" || groupIdentifier.endsWith(":tenant-admin");
}

export function hasTenantAdminGroup(groupIdentifiers: string[]): boolean {
  return groupIdentifiers.some((group) => isTenantAdminGroup(group));
}

