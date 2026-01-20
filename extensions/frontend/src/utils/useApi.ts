/**
 * useApi - Hook for making API calls in extensions
 * 
 * Provides access to HttpService methods for extension components
 */

import HttpService from '../services/HttpService';

/**
 * useApi - Hook to access API methods
 * @returns API methods from HttpService
 */
export function useApi() {
  return {
    makeCallToBackend: HttpService.makeCallToBackend,
    HttpMethods: HttpService.HttpMethods,
    messageForHttpError: HttpService.messageForHttpError,
  };
}

export default useApi;
