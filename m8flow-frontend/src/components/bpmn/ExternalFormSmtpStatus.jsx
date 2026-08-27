import React from 'react';
import { useEffect, useState } from '@bpmn-io/properties-panel/preact/hooks';
import { getSmtpStatus } from '../../services/ExternalFormNotificationService';

/**
 * SMTP readiness for the External Form properties group.
 *
 * Setting an External form URL promises the assignee an email, but SMTP lives in tenant
 * secrets configured somewhere else entirely — so without this the modeler gets no hint
 * that the promise cannot be kept.
 *
 * Rendered by @bpmn-io/properties-panel's bundled preact, so hooks come from its subpath
 * export (the same import upstream's SpiffExtensionTaskMetadata uses).
 */

/**
 * Resolved SMTP status, or null while loading / on any failure.
 *
 * Failure deliberately yields null rather than an error state: the modeler must never
 * break because a status call failed or the user lacks permission to read it.
 *
 * getSmtpStatus caches the in-flight promise per tenant, so the label marker and the
 * detail entry calling this independently still produce a single request.
 */
function useSmtpStatus() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancelled = false;
    try {
      getSmtpStatus()
        .then((result) => {
          if (!cancelled) {
            setStatus(result);
          }
        })
        .catch(() => {});
    } catch {
      // Defensive: getSmtpStatus should return a promise, never throw synchronously.
    }
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}

/**
 * Marker rendered into the group *label*, which lives in the header and stays visible
 * while the group is collapsed.
 *
 * The entries container is `display: none` until the group is expanded, and the panel
 * gives a provider no way to light up the header's own edited/error dot (`isEdited` needs
 * a DOM node that only exists once open; `errors` is a panel-level prop). The label is
 * therefore the only always-visible surface available here.
 */
export function ExternalFormSmtpLabel({ label }) {
  const status = useSmtpStatus();
  const unconfigured = Boolean(status) && !status.configured;

  if (!unconfigured) {
    return label;
  }

  return (
    <span data-testid="external-form-smtp-label">
      {label}{' '}
      <span
        title="Email notifications are not configured for this tenant."
        style={{ color: '#d97706', fontWeight: 'bold' }}
      >
        ⚠
      </span>
    </span>
  );
}

/**
 * The detail shown inside the group once expanded: which tenant secrets are missing.
 * Renders nothing when SMTP is usable, still loading, or unreadable.
 */
export function ExternalFormSmtpStatus() {
  const status = useSmtpStatus();

  if (!status || status.configured) {
    return null;
  }

  const missing = status.missing_required_keys || [];

  return (
    <div
      className="bio-properties-panel-entry"
      data-testid="external-form-smtp-warning"
      style={{ padding: '8px 0' }}
    >
      <div
        style={{
          borderLeft: '3px solid #d97706',
          paddingLeft: '8px',
          fontSize: '12px',
          lineHeight: 1.5,
        }}
      >
        <strong>Email notifications are not configured.</strong> Assignees will
        not receive the secure link until these tenant secrets are set under
        Configuration &gt; Secrets:
        <ul style={{ margin: '4px 0 0 0', paddingLeft: '16px' }}>
          {missing.map((key) => (
            <li key={key}>
              <code>{key}</code>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default ExternalFormSmtpStatus;
