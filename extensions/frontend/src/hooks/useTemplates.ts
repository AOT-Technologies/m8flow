import { useState, useCallback } from 'react';
import HttpService from '../services/HttpService';
import { Template, TemplateFilters } from '../types/template';

const FILTER_PARAM_KEYS: (keyof TemplateFilters)[] = [
  'search',
  'category',
  'tag',
  'visibility',
  'owner',
  'latest_only',
];

function buildTemplateQueryParams(filters?: TemplateFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (!filters) return params;
  for (const key of FILTER_PARAM_KEYS) {
    const value = filters[key];
    if (value !== undefined && value !== null) {
      params.append(key, typeof value === 'boolean' ? String(value) : value);
    }
  }
  return params;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err != null && typeof err === 'object' && 'message' in err && typeof (err as { message: unknown }).message === 'string') {
    return (err as { message: string }).message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

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

    const params = buildTemplateQueryParams(filters);
    const queryString = params.toString();
    const path = `/v1.0/m8flow/templates${queryString ? `?${queryString}` : ''}`;

    HttpService.makeCallToBackend({
      path,
      httpMethod: HttpService.HttpMethods.GET,
      successCallback: (result: Template[]) => {
        setTemplates(result);
        setLoading(false);
      },
      failureCallback: (err: unknown) => {
        setError(getErrorMessage(err, 'Failed to fetch templates'));
        setLoading(false);
        if (process.env.NODE_ENV === 'development') {
          console.error('Error fetching templates:', err);
        }
      },
    });
  }, []);

  const fetchTemplateById = useCallback((id: number): Promise<Template | null> => {
    return new Promise((resolve) => {
      setLoading(true);
      setError(null);

      HttpService.makeCallToBackend({
        path: `/v1.0/m8flow/templates/${id}`,
        httpMethod: HttpService.HttpMethods.GET,
        successCallback: (result: Template) => {
          setLoading(false);
          resolve(result);
        },
        failureCallback: (err: unknown) => {
          setError(getErrorMessage(err, 'Failed to fetch template'));
          setLoading(false);
          if (process.env.NODE_ENV === 'development') {
            console.error('Error fetching template by ID:', err);
          }
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
        const path = `/v1.0/m8flow/templates/${key}${queryString ? `?${queryString}` : ''}`;

        HttpService.makeCallToBackend({
          path,
          httpMethod: HttpService.HttpMethods.GET,
          successCallback: (result: Template) => {
            setLoading(false);
            resolve(result);
          },
          failureCallback: (err: unknown) => {
            setError(getErrorMessage(err, 'Failed to fetch template'));
            setLoading(false);
            if (process.env.NODE_ENV === 'development') {
              console.error('Error fetching template by key:', err);
            }
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
