/**
 * Process model diagram editor — delegate to upstream.
 *
 * Former fork mainly rewired imports to @spiffworkflow-frontend, swapped in
 * M8flowUriListForPermissions, and restyled the form-builder shell. URI coverage
 * remains via hooks/UriListForPermissions; form chrome reverts to upstream.
 */
export { default } from '@spiff-core/views/ProcessModelEditDiagram';
