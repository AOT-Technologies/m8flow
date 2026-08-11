import React from 'react';
import { useEffect, useState } from '@bpmn-io/properties-panel/preact/hooks';
import { getSmtpStatus } from '../../services/ExternalFormNotificationService';

/**
 * Warning shown inside the "Web Form (External Form)" properties group when the tenant
 * has not configured the SMTP secrets the notification worker needs.
 *
 * Without this, setting an External form URL silently promises an email that will never
 * be sent: SMTP lives in tenant secrets, which are configured somewhere else entirely.
 *
 * Rendered by @bpmn-io/properties-panel's bundled preact, so hooks come from its subpath
 * export (the same import upstream's SpiffExtensionTaskMetadata uses). Every failure path
 * renders nothing — the modeler must never break because a status call failed or the user
 * lacks permission to read it.
 */
export function ExternalFormSmtpStatus() {
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
        <strong>Email notifications are not configured.</strong> Assignees will not receive
        the secure link until these tenant secrets are set under Configuration &gt; Secrets:
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
