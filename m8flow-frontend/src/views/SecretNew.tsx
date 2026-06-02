/**
 * Re-export the upstream SecretNew component.
 *
 * Configuration.tsx imports SecretNew from this relative path.
 * Unlike SecretList and SecretShow, this component does not need
 * any M8Flow-specific overrides, so we simply re-export it.
 */
export { default } from '@spiffworkflow-frontend/views/SecretNew';
