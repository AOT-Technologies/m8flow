export const DEFAULT_API_VERSION = '1.0';
export const SUPPORTED_API_VERSIONS = ['1.0', '2.0'] as const;

export type ApiVersion = (typeof SUPPORTED_API_VERSIONS)[number];

export type ApiVersionBuildEnvironment = {
  VITE_API_VERSION?: string | null;
  M8FLOW_API_VERSION?: string | null;
};

export type ApiVersionBuildConfig = {
  version: ApiVersion;
  /** JSON literal consumed by Vite's `define` option. */
  defineValue: string;
  /** Versioned Vite proxy paths derived from the same supported-version registry. */
  proxyPaths: string[];
};

export function resolveApiVersion(value?: string | null): ApiVersion {
  const version = value?.trim() || DEFAULT_API_VERSION;
  if (!(SUPPORTED_API_VERSIONS as readonly string[]).includes(version)) {
    throw new Error(
      `Unsupported M8Flow API version "${version}". Supported versions: ${SUPPORTED_API_VERSIONS.join(', ')}.`,
    );
  }
  return version as ApiVersion;
}

/** Resolve the API version using the same precedence as the Vite build. */
export function resolveBuildApiVersion(environment: ApiVersionBuildEnvironment): ApiVersion {
  return resolveApiVersion(environment.VITE_API_VERSION ?? environment.M8FLOW_API_VERSION);
}

/** Build the values Vite uses for the bundled API version and development proxy. */
export function resolveApiVersionBuildConfig(
  environment: ApiVersionBuildEnvironment,
): ApiVersionBuildConfig {
  const version = resolveBuildApiVersion(environment);
  return {
    version,
    defineValue: JSON.stringify(version),
    proxyPaths: SUPPORTED_API_VERSIONS.map((supportedVersion) => `/v${supportedVersion}`),
  };
}

export function pathForApiVersion(path: string, version: string): string {
  const prefix = `/v${resolveApiVersion(version)}`;
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const versionPrefix = /^\/v\d+(?:\.\d+)?(?=\/|$)/;
  return versionPrefix.test(normalized)
    ? normalized.replace(versionPrefix, prefix)
    : `${prefix}${normalized}`;
}
