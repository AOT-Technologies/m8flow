export const SUPPORTED_API_VERSIONS = ['1.0', '2.0'] as const;

export type ApiVersion = (typeof SUPPORTED_API_VERSIONS)[number];

/** Validate the designer's build-time API contract setting. */
export function resolveConfiguredApiVersion(value: string | undefined): ApiVersion {
  const version = value?.trim() || '1.0';
  if (!SUPPORTED_API_VERSIONS.includes(version as ApiVersion)) {
    throw new Error(
      `Unsupported VITE_API_VERSION "${version}". Supported values: ${SUPPORTED_API_VERSIONS.join(', ')}.`,
    );
  }
  return version as ApiVersion;
}
