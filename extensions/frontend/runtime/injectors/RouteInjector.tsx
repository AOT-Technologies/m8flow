import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { SampleView } from '../../views/SampleView';
import { useExtension } from '../../contexts/ExtensionContext';

/**
 * Route Injector
 * 
 * Intercepts custom routes and renders custom views without modifying upstream routing.
 * Uses React Portal to inject custom views into the main content area.
 * 
 * Note: This approach works by detecting custom routes and rendering our view
 * alongside React Router's rendering. The upstream router will show a 404 or default
 * route, but our portal will overlay our custom view.
 */
export function RouteInjector() {
  const [mainContent, setMainContent] = useState<Element | null>(null);
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const { isFeatureEnabled } = useExtension();
  
  // Listen to route changes - check periodically and on events
  useEffect(() => {
    const updatePath = () => {
      const newPath = window.location.pathname;
      if (newPath !== currentPath) {
        setCurrentPath(newPath);
      }
    };
    
    // Check immediately
    updatePath();
    
    // Listen to popstate (back/forward buttons)
    window.addEventListener('popstate', updatePath);
    
    // Poll for changes (React Router might not trigger popstate)
    const intervalId = setInterval(updatePath, 100);
    
    return () => {
      window.removeEventListener('popstate', updatePath);
      clearInterval(intervalId);
    };
  }, [currentPath]);
  
  useEffect(() => {
    if (!isFeatureEnabled('customRoutes')) {
      return;
    }
    
    // Find the main content area where routes are rendered
    const findMainContent = () => {
      // Strategy 1: Look for the container-for-extensions-box-2 (from ContainerForExtensions)
      const container = document.querySelector('#container-for-extensions-box-2');
      if (container) {
        return container as Element;
      }
      
      // Strategy 2: Look for Box with component="main" (from BaseRoutes)
      const mainBox = document.querySelector('div[class*="MuiBox-root"][component="main"]');
      if (mainBox) {
        return mainBox as Element;
      }
      
      // Strategy 3: Look for any large Box that's not the sidebar
      const allBoxes = document.querySelectorAll('div[class*="MuiBox-root"]');
      for (const box of Array.from(allBoxes)) {
        const rect = box.getBoundingClientRect();
        const styles = window.getComputedStyle(box);
        
        // Skip if hidden or too small
        if (styles.display === 'none' || rect.width < 300 || rect.height < 200) {
          continue;
        }
        
        // Skip sidebar (usually on the left, narrow width)
        if (rect.left < 100 && rect.width < 400) {
          continue;
        }
        
        // Check if it contains route content (has links, headings, etc.)
        const hasContent = box.querySelector('h1, h2, h3, [role="main"], main, table, .MuiContainer-root');
        if (hasContent || rect.width > 500) {
          return box as Element;
        }
      }
      
      // Strategy 4: Fallback to body if nothing else works (last resort)
      return document.body;
    };
    
    // Try to find container immediately
    const tryFind = () => {
      const container = findMainContent();
      if (container) {
        setMainContent(container);
        return true;
      }
      return false;
    };
    
    // Try immediately
    if (!tryFind()) {
      // If not found, set up observer and retry with delays
      const observer = new MutationObserver(() => {
        if (!mainContent) {
          tryFind();
        }
      });
      
      observer.observe(document.body, { 
        childList: true, 
        subtree: true,
      });
      
      // Also retry after delays
      const timeout1 = setTimeout(() => {
        if (!mainContent) tryFind();
      }, 500);
      
      const timeout2 = setTimeout(() => {
        if (!mainContent) tryFind();
      }, 2000);
      
      return () => {
        observer.disconnect();
        clearTimeout(timeout1);
        clearTimeout(timeout2);
      };
    }
    
    return () => {};
  }, [currentPath, isFeatureEnabled]); // Remove mainContent from deps to allow re-searching
  
  // Check if we're on a custom route
  const isCustomRoute = currentPath === '/sample-page';
  
  // Clear the container and inject our custom view - MUST be called before any conditional returns
  useEffect(() => {
    if (mainContent && isCustomRoute) {
      // Clear existing content but be more selective
      const children = Array.from(mainContent.children);
      children.forEach((child) => {
        const id = child.id || '';
        const className = child.className || '';
        
        // Keep error displays, verification banner, and our injected content
        if (
          !id.includes('error') && 
          !id.includes('Error') &&
          !className.includes('MuiAlert') &&
          !child.hasAttribute('data-m8flow-injected')
        ) {
          (child as HTMLElement).style.display = 'none';
        }
      });
    }
  }, [mainContent, isCustomRoute]);
  
  if (!isCustomRoute || !isFeatureEnabled('customRoutes')) {
    return null;
  }
  
  // If no container found, render directly (fallback)
  if (!mainContent) {
    return (
      <div 
        data-m8flow-injected="true"
        style={{ 
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          width: '100%',
          height: '100%',
          padding: '20px',
          backgroundColor: 'white',
          zIndex: 9999,
          overflow: 'auto',
        }}
      >
        <SampleView />
      </div>
    );
  }
  
  // Inject custom view into main content area
  return createPortal(
    <div 
      data-m8flow-injected="true"
      style={{ 
        width: '100%', 
        minHeight: '100%',
        padding: '20px',
        position: 'relative',
        zIndex: 10,
        backgroundColor: 'white', // Ensure it's visible
      }}
    >
      <SampleView />
    </div>,
    mainContent
  );
}
