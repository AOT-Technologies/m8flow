/**
 * useService - Hook to access core services in extensions
 * 
 * Provides access to services like UserService
 */

import UserService from '../services/UserService';

/**
 * useService - Get services from core
 * @returns Services object with all available services
 */
export function useService() {
  return {
    UserService,
  };
}

export default useService;
