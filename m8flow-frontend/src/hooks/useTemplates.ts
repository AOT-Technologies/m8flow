import { useState, useCallback } from 'react';
import HttpService from '../services/HttpService';
import { Template, TemplateFilters } from '../types/template';
import { normalizeTemplate } from '../utils/templateHelpers';
import { PaginationObject } from '@spiffworkflow-frontend/interfaces';

const FILTER_PARAM_KEYS: (keyof TemplateFilters)[] = [
  'search',
  'category',
  'tag',
  'visibility',
  'owner',
  'latest_only',
  'page',
  'per_page',
];

function buildTemplateQueryParams(filters?: TemplateFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (!filters) return params;
  for (const key of FILTER_PARAM_KEYS) {
    const value = filters[key];
    if (value !== undefined && value !== null) {
      params.append(key, typeof value === 'boolean' ? String(value) : String(value));
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
  pagination: PaginationObject | null;
  templatesLoading: boolean;
  templateByIdLoading: boolean;
  templateByKeyLoading: boolean;
  error: string | null;
  fetchTemplates: (filters?: TemplateFilters) => void;
  fetchTemplateById: (id: number) => Promise<Template | null>;
  fetchTemplateByKey: (key: string, version?: string) => Promise<Template | null>;
}

export function useTemplates(): UseTemplatesReturn {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [pagination, setPagination] = useState<PaginationObject | null>(null);
  const [templatesLoading, setTemplatesLoading] = useState<boolean>(false);
  const [templateByIdLoading, setTemplateByIdLoading] = useState<boolean>(false);
  const [templateByKeyLoading, setTemplateByKeyLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback((filters?: TemplateFilters) => {
    setTemplatesLoading(true);
    setError(null);

    const params = buildTemplateQueryParams(filters);
    const queryString = params.toString();
    const path = `/v1.0/m8flow/templates${queryString ? `?${queryString}` : ''}`;

    HttpService.makeCallToBackend({
      path,
      httpMethod: HttpService.HttpMethods.GET,
      successCallback: (result: Record<string, unknown>) => {
        const results = result.results as Record<string, unknown>[];
        const pag = result.pagination as PaginationObject | undefined;
        setTemplates(Array.isArray(results) ? results.map((r) => normalizeTemplate(r)) : []);
        setPagination(pag ?? null);
        setTemplatesLoading(false);
      },
      failureCallback: (err: unknown) => {
        setError(getErrorMessage(err, 'Failed to fetch templates'));
        setTemplatesLoading(false);
        if (process.env.NODE_ENV === 'development') {
          console.error('Error fetching templates:', err);
        }
      },
    });
  }, []);

  const fetchTemplateById = useCallback((id: number): Promise<Template | null> => {
    return new Promise((resolve) => {
      setTemplateByIdLoading(true);
      setError(null);

      HttpService.makeCallToBackend({
        path: `/v1.0/m8flow/templates/${id}`,
        httpMethod: HttpService.HttpMethods.GET,
        successCallback: (result: Record<string, unknown>) => {
          setTemplateByIdLoading(false);
          resolve(normalizeTemplate(result));
        },
        failureCallback: (err: unknown) => {
          setError(getErrorMessage(err, 'Failed to fetch template'));
          setTemplateByIdLoading(false);
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
        setTemplateByKeyLoading(true);
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
          successCallback: (result: Record<string, unknown>) => {
            setTemplateByKeyLoading(false);
            resolve(normalizeTemplate(result));
          },
          failureCallback: (err: unknown) => {
            setError(getErrorMessage(err, 'Failed to fetch template'));
            setTemplateByKeyLoading(false);
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
    pagination,
    templatesLoading,
    templateByIdLoading,
    templateByKeyLoading,
    error,
    fetchTemplates,
    fetchTemplateById,
    fetchTemplateByKey,
  };
}

export default useTemplates;
