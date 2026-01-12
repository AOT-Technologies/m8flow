/**
 * M8Flow Extension Types
 */

export type { BuildVariant, VariantConfig } from '../config/variants';

export interface ExtensionConfig {
  enableMultiTenancy?: boolean;
  enableAdvancedIntegrations?: boolean;
  [key: string]: unknown;
}

export interface ExtensionPoint {
  name: string;
  component: React.ComponentType;
}
