import { useActiveTenant } from '@/components/session/hooks';
import { HomeStatsGrid } from './components/HomeStatsGrid';
import { MyTasksList } from './components/MyTasksList';
import { RecentInstancesTable } from './components/RecentInstancesTable';

export default function HomePage() {
  const { scopedTenantId, isSuperAdmin } = useActiveTenant();

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">Home</h1>
      </div>
      <div className="flex flex-col gap-8">
        <HomeStatsGrid tenantId={scopedTenantId} showTotalTenants={isSuperAdmin} />
        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <RecentInstancesTable tenantId={scopedTenantId} />
          <MyTasksList tenantId={scopedTenantId} />
        </div>
      </div>
    </main>
  );
}
