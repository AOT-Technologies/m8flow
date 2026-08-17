/**
 * Configuration route table — kept separate from the tab shell for CPD.
 */
import { Route, Routes } from 'react-router-dom';
import Extension from '../views/Extension';
import ExternalFormEmailConfigure from '../views/ExternalFormEmailConfigure';
import SecretList from '../views/SecretList';
import SecretNew from '../views/SecretNew';
import SecretShow from '../views/SecretShow';

export function ConfigurationRoutes() {
  return (
    <Routes>
      <Route path="/" element={<SecretList />} />
      <Route path="secrets" element={<SecretList />} />
      <Route path="secrets/new" element={<SecretNew />} />

      {/* M8Flow: guided NATS_SMTP_* entry, reached from the Secrets page banner.
          Deliberately not a tab — it is a task, not a section. Declared before
          the :secret_identifier route so it is not swallowed as a secret key. */}
      <Route
        path="external-form-email"
        element={<ExternalFormEmailConfigure />}
      />

      <Route path="secrets/:secret_identifier" element={<SecretShow />} />

      <Route
        path="extension/:page_identifier"
        element={<Extension displayErrors={false} />}
      />
    </Routes>
  );
}