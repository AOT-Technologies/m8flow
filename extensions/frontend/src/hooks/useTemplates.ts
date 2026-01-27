import { useState, useCallback } from 'react';
import HttpService from '../services/HttpService';
import { Template, TemplateFilters } from '../types/template';

interface UseTemplatesReturn {
  templates: Template[];
  loading: boolean;
  error: string | null;
  fetchTemplates: (filters?: TemplateFilters) => void;
  fetchTemplateById: (id: number) => Promise<Template | null>;
  fetchTemplateByKey: (key: string, version?: string) => Promise<Template | null>;
}

export function useTemplates(): UseTemplatesReturn {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback((filters?: TemplateFilters) => {
    setLoading(true);
    setError(null);

    // Build query parameters
    const params = new URLSearchParams();
    if (filters?.search) {
      params.append('search', filters.search);
    }
    if (filters?.category) {
      params.append('category', filters.category);
    }
    if (filters?.tag) {
      params.append('tag', filters.tag);
    }
    if (filters?.visibility) {
      params.append('visibility', filters.visibility);
    }
    if (filters?.owner) {
      params.append('owner', filters.owner);
    }
    if (filters?.latest_only !== undefined) {
      params.append('latest_only', filters.latest_only.toString());
    }

    const queryString = params.toString();
    const path = `/v1.0/templates${queryString ? `?${queryString}` : ''}`;

    HttpService.makeCallToBackend({
      path,
      httpMethod: HttpService.HttpMethods.GET,
      successCallback: (result: Template[]) => {
        setTemplates(result);
        setLoading(false);
      },
      failureCallback: (err: any) => {
        const errorMessage = err?.message || 'Failed to fetch templates';
        setError(errorMessage);
        setLoading(false);
        console.error('Error fetching templates:', err);
      },
    });
  }, []);

  const fetchTemplateById = useCallback((id: number): Promise<Template | null> => {
    return new Promise((resolve) => {
      setLoading(true);
      setError(null);

      HttpService.makeCallToBackend({
        path: `/v1.0/templates/${id}`,
        httpMethod: HttpService.HttpMethods.GET,
        successCallback: (result: Template) => {
          setLoading(false);
          resolve(result);
        },
        failureCallback: (err: any) => {
          const errorMessage = err?.message || 'Failed to fetch template';
          setError(errorMessage);
          setLoading(false);
          console.error('Error fetching template by ID:', err);
          resolve(null);
        },
      });
    });
  }, []);

  const fetchTemplateByKey = useCallback(
    (key: string, version?: string): Promise<Template | null> => {
      return new Promise((resolve) => {
        setLoading(true);
        setError(null);

        const params = new URLSearchParams();
        if (version) {
          params.append('version', version);
        } else {
          params.append('latest', 'true');
        }

        const queryString = params.toString();
        const path = `/v1.0/templates/${key}${queryString ? `?${queryString}` : ''}`;

        HttpService.makeCallToBackend({
          path,
          httpMethod: HttpService.HttpMethods.GET,
          successCallback: (result: Template) => {
            setLoading(false);
            resolve(result);
          },
          failureCallback: (err: any) => {
            const errorMessage = err?.message || 'Failed to fetch template';
            setError(errorMessage);
            setLoading(false);
            console.error('Error fetching template by key:', err);
            resolve(null);
          },
        });
      });
    },
    [],
  );

  return {
    templates,
    loading,
    error,
    fetchTemplates,
    fetchTemplateById,
    fetchTemplateByKey,
  };
}

export default useTemplates;
