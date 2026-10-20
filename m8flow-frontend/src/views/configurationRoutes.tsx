/**
 * Configuration route table — kept separate from the tab shell for CPD.
 */
import { Route, Routes } from 'react-router-dom';
import Extension from '../views/Extension';
import NamedValueList from '../views/NamedValueList';
import SecretNew from '../views/SecretNew';
import SecretShow from '../views/SecretShow';

export function ConfigurationRoutes() {
  return (
    <Routes>
      <Route path="/" element={<NamedValueList />} />
      <Route path="secrets" element={<NamedValueList />} />
      <Route path="secrets/new" element={<SecretNew />} />
      <Route path="secrets/:secret_identifier" element={<SecretShow />} />
      <Route path="named-values" element={<NamedValueList />} />
      <Route
        path="extension/:page_identifier"
        element={<Extension displayErrors={false} />}
      />
    </Routes>
  );
}
