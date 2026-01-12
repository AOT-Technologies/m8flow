import React, { ComponentType } from 'react';
import { ExtensionProvider } from '../contexts/ExtensionContext';
import { NavigationInjector } from './injectors/NavigationInjector';
import { RouteInjector } from './injectors/RouteInjector';
import { VerificationBanner } from '../components/VerificationBanner';

/**
 * Wraps the upstream App component with M8Flow extensions
 * 
 * This HOC provides:
 * - Extension context for feature flags
 * - Logo injection via React Portal
 * - Navigation item injection
 * - Custom route handling
 * - Verification banner (dev only)
 */
export function wrapWithExtensions<P extends object>(
  UpstreamApp: ComponentType<P>
): ComponentType<P> {
  return function M8FlowApp(props: P) {
    const variant = import.meta.env.M8FLOW_VARIANT;
    
    if (variant === 'spiff') {
      // Pure upstream, no extensions
      return <UpstreamApp {...props} />;
    }
    
    // M8Flow variant with extensions
    return (
      <ExtensionProvider>
        <VerificationBanner />
        <NavigationInjector />
        <RouteInjector />
        <UpstreamApp {...props} />
      </ExtensionProvider>
    );
  };
}
