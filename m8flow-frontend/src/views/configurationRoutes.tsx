/**
 * Configuration route table — kept separate from the tab shell for CPD.
 */
import { Route, Routes } from 'react-router-dom';
import Extension from '../views/Extension';
import SecretList from '../views/SecretList';
import SecretNew from '../views/SecretNew';
import SecretShow from '../views/SecretShow';

export function ConfigurationRoutes() {
  return (
    <Routes>
      <Route path="/" element={<SecretList />} />
      <Route path="secrets" element={<SecretList />} />
      <Route path="secrets/new" element={<SecretNew />} />
      <Route path="secrets/:secret_identifier" element={<SecretShow />} />
      <Route
        path="extension/:page_identifier"
        element={<Extension displayErrors={false} />}
      />
    </Routes>
  );
}
