import { ChevronDown, ChevronRight, RefreshCw, Wrench } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { Pill } from '@/components/library/pill/Pill';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { useCapabilities } from '@/components/session/hooks';
import { Button } from '@/components/ui/button';
import i18n from '@/i18n';
import {
  fetchMcpToolsCatalog,
  mcpErrorMessage,
  pingMcpServer,
  type McpPing,
  type McpTool,
  type McpToolsCatalog,
} from '@/lib/mcpToolsApi';

import { McpToolTryIt } from './McpToolTryIt';

const ALL_CATEGORIES = '';

/** "process-instances" -> "Process Instances": categories are the tools' FastMCP tag slugs. */
function humanizeCategory(category: string): string {
  return category
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** Rendered on its own, never inside the catalog block: when the catalog fails this is
 * the only diagnosis the admin gets (M8F-539). */
function PingStatus({ ping, failed }: { ping: McpPing | null; failed: boolean }) {
  const { t } = useTranslation();
  if (failed) return <Pill tone="error">{t('mcpTools.ping.failed')}</Pill>;
  if (!ping) return null;
  if (ping.ok) return <Pill tone="success">{t('mcpTools.ping.connected', { latency: ping.latency_ms })}</Pill>;
  return <Pill tone="error">{ping.authorized ? t('mcpTools.ping.unreachable') : t('mcpTools.ping.notAuthorized')}</Pill>;
}

function ToolRow({ tool, canExecute }: { tool: McpTool; canExecute: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <li className="rounded-lg border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Chevron className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="font-mono text-sm font-medium">{tool.name}</span>
          <span className="block text-sm text-muted-foreground">{tool.description}</span>
        </span>
        <Pill tone={tool.badge === 'read' ? 'success' : 'warning'} dot={false}>
          {tool.badge === 'read' ? t('mcpTools.badge.read') : t('mcpTools.badge.write')}
        </Pill>
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3">
          {tool.parameters.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('mcpTools.parameters.none')}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-1 pr-4 font-medium">{t('common.name')}</th>
                  <th className="py-1 pr-4 font-medium">{t('mcpTools.parameters.type')}</th>
                  <th className="py-1 pr-4 font-medium">{t('common.description')}</th>
                  <th className="py-1 font-medium">{t('mcpTools.parameters.required')}</th>
                </tr>
              </thead>
              <tbody>
                {tool.parameters.map((param) => (
                  <tr key={param.name} className="border-t border-border">
                    <td className="py-1.5 pr-4 font-mono">{param.name}</td>
                    <td className="py-1.5 pr-4 text-muted-foreground">{param.type || '—'}</td>
                    <td className="py-1.5 pr-4 text-muted-foreground">{param.description || '—'}</td>
                    <td className="py-1.5">
                      <Pill tone={param.required ? 'warning' : 'muted'} dot={false}>
                        {param.required ? t('mcpTools.parameters.requiredBadge') : t('mcpTools.parameters.optionalBadge')}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canExecute && <McpToolTryIt tool={tool} />}
        </div>
      )}
    </li>
  );
}

export default function McpToolsPage() {
  const { t } = useTranslation();
  const { canExecuteMcpTools } = useCapabilities();
  const [catalog, setCatalog] = useState<McpToolsCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [ping, setPing] = useState<McpPing | null>(null);
  const [pingFailed, setPingFailed] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState(ALL_CATEGORIES);

  const loadCatalog = useCallback(() => {
    setLoading(true);
    setCatalogError(null);
    fetchMcpToolsCatalog()
      .then(setCatalog)
      .catch((err: unknown) => {
        setCatalog(null);
        setCatalogError(
          mcpErrorMessage(err, i18n.t('mcpTools.catalogErrorFallback')),
        );
      })
      .finally(() => setLoading(false));
  }, []);

  const loadPing = useCallback(() => {
    setPinging(true);
    pingMcpServer()
      .then((result) => {
        setPing(result);
        setPingFailed(false);
      })
      .catch(() => {
        setPing(null);
        setPingFailed(true);
      })
      .finally(() => setPinging(false));
  }, []);

  useEffect(() => {
    loadCatalog();
    loadPing();
  }, [loadCatalog, loadPing]);

  const testConnection = () => {
    loadPing();
    if (!catalog) loadCatalog();
  };

  const categories = useMemo(() => [...new Set((catalog?.tools ?? []).map((t) => t.category))].sort(), [catalog]);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const byCategory = new Map<string, McpTool[]>();
    for (const tool of catalog?.tools ?? []) {
      if (category !== ALL_CATEGORIES && tool.category !== category) continue;
      if (needle && !`${tool.name} ${tool.description}`.toLowerCase().includes(needle)) continue;
      byCategory.set(tool.category, [...(byCategory.get(tool.category) ?? []), tool]);
    }
    return [...byCategory.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [catalog, category, query]);

  return (
    <main className="flex-1 px-11 py-10" data-testid="mcp-tools-page">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-border bg-card p-6">
          <div className="flex items-start gap-3">
            <Wrench className="mt-1 size-5" aria-hidden />
            <div>
              <h1 className="text-xl font-semibold">{t('mcpTools.title')}</h1>
              <p className="text-sm text-muted-foreground">
                {t('mcpTools.subtitle')}
              </p>
              {catalog && (
                <p className="mt-2 font-mono text-xs text-muted-foreground" data-testid="mcp-tools-server-info">
                  {t('mcpTools.serverInfo', {
                    url: catalog.server_url,
                    version: catalog.protocol_version,
                    count: catalog.tool_count,
                  })}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <PingStatus ping={ping} failed={pingFailed} />
            <Button variant="outline" onClick={testConnection} disabled={pinging}>
              <RefreshCw className={pinging ? 'animate-spin' : undefined} aria-hidden />
              {t('mcpTools.testConnection')}
            </Button>
          </div>
        </header>

        {catalogError && (
          <Alert tone="error" data-testid="mcp-tools-catalog-error">
            <p className="font-medium">{t('mcpTools.catalogError')}</p>
            <p className="text-sm">{catalogError}</p>
          </Alert>
        )}

        {!canExecuteMcpTools && (
          <Alert tone="info" data-testid="mcp-tools-read-only-notice">
            {t('mcpTools.readOnlyNotice')}
          </Alert>
        )}

        {loading && !catalog && <p role="status">{t('mcpTools.loading')}</p>}

        {catalog && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <SearchBar value={query} onChange={setQuery} placeholder={t('mcpTools.searchPlaceholder')} className="flex-1" />
              <select
                aria-label={t('mcpTools.category')}
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="h-9 rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value={ALL_CATEGORIES}>{t('mcpTools.allCategories')}</option>
                {categories.map((name) => (
                  <option key={name} value={name}>
                    {humanizeCategory(name)}
                  </option>
                ))}
              </select>
            </div>
            {groups.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('mcpTools.noMatches')}</p>
            ) : (
              groups.map(([name, tools]) => (
                <section key={name} aria-label={humanizeCategory(name)} className="space-y-2">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    {humanizeCategory(name)} <span className="font-normal">({tools.length})</span>
                  </h2>
                  <ul className="space-y-2">
                    {tools.map((tool) => (
                      <ToolRow key={tool.name} tool={tool} canExecute={canExecuteMcpTools} />
                    ))}
                  </ul>
                </section>
              ))
            )}
          </>
        )}
      </div>
    </main>
  );
}
