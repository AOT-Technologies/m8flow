export type BuildVariant = 'spiff' | 'm8flow';

export interface VariantConfig {
  name: string;
  branding: {
    logo: string;
    title: string;
    favicon: string;
  };
  features: {
    customNavigation: boolean;
    customRoutes: boolean;
    multiTenancy: boolean;
    advancedIntegrations: boolean;
  };
}

export const VARIANTS: Record<BuildVariant, VariantConfig> = {
  spiff: {
    name: 'SpiffWorkflow',
    branding: {
      logo: 'spiff-logo',
      title: 'Spiffworkflow',
      favicon: '/favicon-spiff.ico',
    },
    features: {
      customNavigation: false,
      customRoutes: false,
      multiTenancy: false,
      advancedIntegrations: false,
    },
  },
  m8flow: {
    name: 'M8Flow',
    branding: {
      logo: 'm8flow-logo',
      title: 'M8Flow',
      favicon: '/favicon-m8flow.ico',
    },
    features: {
      customNavigation: true,
      customRoutes: true,
      multiTenancy: true,
      advancedIntegrations: true,
    },
  },
};

export function getVariantConfig(): VariantConfig {
  const variant = (import.meta.env.M8FLOW_VARIANT || 'm8flow') as BuildVariant;
  return VARIANTS[variant];
}
