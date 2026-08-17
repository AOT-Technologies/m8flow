/**
 * Task list — super-admin table mode uses TenantTaskTable; otherwise upstream.
 */
import UpstreamTaskTable from '@spiff-core/components/TaskTable';
import UserService from '../services/UserService';
import TenantTaskTable from './TenantTaskTable';

export default function TaskTable(props: {
  entries: any;
  viewMode?: string;
  showNonActive?: boolean;
}) {
  const mode = props.viewMode ?? 'table';
  if (mode === 'table' && UserService.isSuperAdmin()) {
    return (
      <TenantTaskTable
        entries={props.entries}
        showNonActive={props.showNonActive ?? false}
      />
    );
  }
  return <UpstreamTaskTable {...props} />;
}
