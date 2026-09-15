import { useMemo, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';

import { Button } from '@/components/ui/button';
import { Dialog, DialogOverlay, DialogPortal } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

/**
 * "Search" button on the Call Activity properties group
 * (`spiff.callactivity.search` — no reference implementation to port:
 * m8flow-frontend's own `onSearchProcessModels` is a no-op in its one real
 * consumer). Reuses the same search-filter convention
 * ProcessesModelsList.tsx already uses (case-insensitive substring across
 * display name, id, and group), so this behaves like the rest of the app's
 * process-model search rather than inventing a new one.
 */
export type CallActivitySearchProcessModel = {
  id: string;
  displayName: string;
  groupDisplayName: string;
};

export type CallActivitySearchSession = {
  processModels: CallActivitySearchProcessModel[];
  /** The Called Element field's current value, if any — preseeds the query
   * so re-opening Search on an already-configured call activity starts
   * scoped to its current target. */
  initialQuery?: string;
  onSelect: (processModelId: string) => void;
};

export type CallActivitySearchDialogProps = {
  session: CallActivitySearchSession;
  onClose: () => void;
};

export function CallActivitySearchDialog({ session, onClose }: CallActivitySearchDialogProps) {
  const [query, setQuery] = useState(session.initialQuery ?? '');
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === '') return session.processModels;
    return session.processModels.filter(
      (m) =>
        m.displayName.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        m.groupDisplayName.toLowerCase().includes(q),
    );
  }, [session.processModels, query]);

  const handleSelect = (processModelId: string) => {
    session.onSelect(processModelId);
    onClose();
  };

  return (
    // Always mounted-when-rendered (the parent conditionally mounts/unmounts
    // this component rather than passing an `open` boolean — see
    // BpmnCanvas.tsx), so `open` is fixed `true`; `onOpenChange` still wires
    // Radix's own Escape/outside-click dismissal into the same `onClose`
    // the Close button and row-selection already use. Both are new
    // capabilities this dialog didn't have before (it previously had no
    // Escape or outside-click handling at all) — a deliberate gain from
    // adopting the shared primitive, not silently introduced: see this
    // ticket's resolution.
    <Dialog open onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogPortal>
        {/* `DialogPrimitive.Content` used directly (not the shared
            `DialogContent` wrapper) for the same reason as
            ProcessGroupsPicker: this dialog's top-anchored 560px layout
            doesn't fit the wrapper's centered small-modal default.
            `overlayClassName` supplies this dialog's own `bg-black/40`
            tint. */}
        <DialogOverlay className="z-[1000] bg-black/40" />
        <DialogPrimitive.Content
          aria-label="Search process models"
          onOpenAutoFocus={(event) => {
            // Radix's default open-focus targets the Content element
            // itself; this dialog wants the search input focused instead
            // (its previous `autoFocus` intent), so take over explicitly
            // rather than race a native `autoFocus` attribute against
            // Radix's own focus-management effect.
            event.preventDefault();
            inputRef.current?.focus();
          }}
          className="fixed top-24 left-1/2 z-[1000] flex max-h-[calc(100vh-120px)] w-[calc(100%-3rem)] max-w-[560px] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl outline-none"
        >
          <div className="flex flex-none items-center justify-between border-b border-border px-5 py-3">
            <h2 className="text-sm font-semibold text-foreground">Select a process model</h2>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={onClose}
              title="Close search"
              aria-label="Close search"
              className="rounded-md text-muted-foreground"
            >
              <X className="size-4" strokeWidth={2} />
            </Button>
          </div>

          <div className="flex flex-none items-center gap-2 border-b border-border px-4 py-2.5">
            <Search className="size-4 flex-none text-muted-foreground" strokeWidth={2} />
            <Input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name, id, or group…"
              aria-label="Search process models"
              className="h-auto w-full border-none bg-transparent p-0 text-sm text-foreground shadow-none outline-none focus-visible:ring-0"
            />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {results.length === 0 ? (
              <p className="px-5 py-6 text-center text-sm text-muted-foreground">
                No process models match &ldquo;{query}&rdquo;.
              </p>
            ) : (
              <ul>
                {results.map((model) => (
                  <li key={model.id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(model.id)}
                      className="flex w-full flex-col items-start gap-0.5 px-5 py-2.5 text-left hover:bg-muted"
                    >
                      <span className="text-sm font-medium text-foreground">{model.displayName}</span>
                      <span className="text-xs text-muted-foreground">
                        {model.groupDisplayName} · {model.id}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
