import { Link, NavLink } from 'react-router-dom';
import { Globe2, ReceiptText, Settings, Users } from 'lucide-react';
import { BrandMark } from '@/components/brand/BrandMark';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/team', label: 'Team', icon: Users },
  { to: '/payments', label: 'Payments', icon: ReceiptText },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export function TopBar() {
  const { tenant } = useAuth();
  const workspaceName = tenant?.tenant.brand_display_name || tenant?.tenant.name || 'OpenSplit';
  const publicSlug = tenant?.tenant.public_slug || workspaceName
    .toLowerCase()
    .trim()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  return (
    <header className="fixed inset-x-0 top-0 z-[60] border-b border-white/[0.06] bg-[#0A0B12]">
      <div className="mx-auto flex min-h-[60px] max-w-[1480px] flex-col gap-1.5 px-4 py-1.5 sm:px-6 lg:min-h-[58px] lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex min-w-0 items-center justify-between gap-4 lg:justify-start">
          <div className="flex items-center gap-2.5">
            <BrandMark size="xs" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white">OpenSplit</p>
            </div>
          </div>
        </div>

        <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 lg:mx-0 lg:flex-1 lg:justify-center">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'inline-flex min-h-8 shrink-0 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-[#94A3B8] transition hover:bg-white/[0.05] hover:text-[#F5F5F7]',
                  isActive && 'border border-[#FF2D78]/18 bg-[#FF2D78]/10 text-[#F5F5F7]'
                )
              }
            >
              <item.icon className="h-4 w-4" strokeWidth={1.8} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <Link
          to={`/public/${publicSlug}`}
          className="hidden min-h-8 items-center justify-center gap-2 rounded-md border border-white/[0.08] bg-white/[0.03] px-3 text-sm font-semibold text-[#F5F5F7] transition hover:border-white/[0.14] hover:bg-white/[0.06] lg:inline-flex"
        >
          <Globe2 className="h-4 w-4 text-[#6B7280]" strokeWidth={1.8} />
          Public teams
        </Link>
      </div>
    </header>
  );
}
