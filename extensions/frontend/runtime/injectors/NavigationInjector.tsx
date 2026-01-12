import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Extension } from '@mui/icons-material';
import { ListItem, ListItemIcon, ListItemText } from '@mui/material';
import { useExtension } from '../../contexts/ExtensionContext';

/**
 * Navigation Injector
 * 
 * Injects custom navigation items into the sidebar without modifying upstream code.
 * Uses React Portal to inject items into the navigation list.
 */
export function NavigationInjector() {
  const [navListContainer, setNavListContainer] = useState<Element | null>(null);
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const { isFeatureEnabled } = useExtension();
  
  // Listen to route changes
  useEffect(() => {
    const updatePath = () => {
      const newPath = window.location.pathname;
      if (newPath !== currentPath) {
        setCurrentPath(newPath);
      }
    };
    
    updatePath();
    window.addEventListener('popstate', updatePath);
    
    // Poll for changes
    const intervalId = setInterval(updatePath, 100);
    
    return () => {
      window.removeEventListener('popstate', updatePath);
      clearInterval(intervalId);
    };
  }, [currentPath]);
  
  useEffect(() => {
    // Only search if we haven't found the container yet
    if (navListContainer) {
      return;
    }
    
    if (!isFeatureEnabled('customNavigation')) {
      return;
    }
    
    // Find the navigation list container
    const findNavContainer = () => {
      
      // Look for MUI List component in the sidebar
      // The List is directly in the SideNav component
      const selectors = [
        // Direct MUI List selector
        'ul[class*="MuiList"]',
        '[class*="MuiList-root"]',
        // Look in sidebar area
        '[class*="MuiBox"] ul[role="list"]',
        // Fallback: any ul with list items
        'ul[role="list"]',
      ];
      
      for (const selector of selectors) {
        const lists = document.querySelectorAll(selector);
        for (const list of Array.from(lists)) {
          // Verify it's the main nav list (has navigation items with links)
          const hasNavItems = list.querySelectorAll('a[href*="/"], [role="listitem"]').length > 0;
          const hasHomeLink = list.textContent?.includes('Home') || list.querySelector('a[href="/"]');
          
          if (hasNavItems && hasHomeLink) {
            return list as Element;
          }
        }
      }
      
      return null;
    };
    
    const observer = new MutationObserver(() => {
      if (!navListContainer) {
        const container = findNavContainer();
        if (container) {
          setNavListContainer(container);
        }
      }
    });
    
    observer.observe(document.body, { 
      childList: true, 
      subtree: true,
    });
    
    // Try immediately
    const container = findNavContainer();
    if (container) {
      setNavListContainer(container);
    }
    
    return () => observer.disconnect();
  }, [isFeatureEnabled]); // Remove navListContainer from deps to prevent infinite loop
  
  if (!navListContainer || !isFeatureEnabled('customNavigation')) {
    return null;
  }
  
  // Check if route is active
  const isActive = currentPath === '/sample-page';
  
  // Create custom navigation item with manual navigation
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    
    // Navigate using window.location for immediate effect
    if (window.location.pathname !== '/sample-page') {
      window.history.pushState({}, '', '/sample-page');
      setCurrentPath('/sample-page');
      
      // Force React Router to update by dispatching popstate
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
  };
  
  const customNavItem = (
    <ListItem 
      component="a"
      href="/sample-page"
      onClick={handleClick}
      selected={isActive}
      sx={{
        cursor: 'pointer',
        '&.Mui-selected': {
          backgroundColor: 'action.selected',
        },
        '&:hover': {
          backgroundColor: 'action.hover',
        },
      }}
    >
      <ListItemIcon>
        <Extension />
      </ListItemIcon>
      <ListItemText primary="Sample Page" />
    </ListItem>
  );
  
  // Inject as a new list item
  return createPortal(customNavItem, navListContainer);
}
