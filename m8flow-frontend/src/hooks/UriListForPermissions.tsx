/**
 * Override: resolve upstream's `useUriListForPermissions` to m8flow's extended
 * URI map (tenant management, templates, connectors, MCP, NATS, …).
 *
 * When core (or a re-exported upstream view) imports
 * `../hooks/UriListForPermissions`, the override resolver picks this file.
 */
export {
  useM8flowUriListForPermissions as useUriListForPermissions,
} from './M8flowUriListForPermissions';
