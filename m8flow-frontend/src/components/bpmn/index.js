import ExternalFormPropertiesProvider from './ExternalFormPropertiesProvider';
import ConnectorProfilePropertiesProvider from './ConnectorProfilePropertiesProvider';

export default {
  __init__: ['externalFormPropertiesProvider'],
  externalFormPropertiesProvider: ['type', ExternalFormPropertiesProvider],
};

/**
 * Adds the "Connector profile" dropdown to the service task group.
 *
 * Kept as a separate module so it can be registered *after*
 * bpmn-js-spiffworkflow, whose service task group it rewrites.
 */
export const connectorProfileModule = {
  __init__: ['connectorProfilePropertiesProvider'],
  connectorProfilePropertiesProvider: [
    'type',
    ConnectorProfilePropertiesProvider,
  ],
};
