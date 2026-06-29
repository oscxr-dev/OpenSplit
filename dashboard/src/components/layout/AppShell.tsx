import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';

export function AppShell() {
  return (
    <div className="opensplit-app min-h-screen">
      <TopBar />

      <main className="px-4 pb-32 pt-20 sm:px-6 sm:pt-20 md:pb-14 lg:px-8 lg:pt-[68px]">
        <div className="mx-auto max-w-[1480px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
