import { NavLink } from 'react-router-dom';
import { Globe2, Settings, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

// mempool.space-style nav item: the active state is a full-height rectangular
// block (square corners, no border/pill) in electric pink, integrated into the
// navbar. Inactive items are plain text with a subtle hover fill.
const navItemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'inline-flex h-full min-h-9 items-center gap-2 px-5 text-sm font-medium transition-colors',
    isActive
      ? 'bg-[#FF2D78] text-[#FFFFFF] hover:bg-[#FF2D78] hover:text-[#FFFFFF] focus-visible:bg-[#FF2D78] focus-visible:text-[#FFFFFF]'
      : 'text-[#94A3B8] hover:bg-transparent hover:text-[#FF2D78]'
  );

const mobileNavItemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'inline-flex min-h-[58px] flex-1 flex-col items-center justify-center gap-1 rounded-2xl text-[11px] font-semibold transition-colors',
    isActive
      ? 'bg-[#FF2D78] text-white hover:bg-[#FF2D78] hover:text-white'
      : 'text-[#94A3B8] hover:bg-white/[0.05] hover:text-[#F5F5F7]'
  );

const navItems = [
  { to: '/team', labelKey: 'nav.team', icon: Users },
  { to: '/public', labelKey: 'nav.publicTeams', icon: Globe2 },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
];

export function TopBar() {
  const { t } = useTranslation();
  return (
    <>
      <header className="fixed inset-x-0 top-0 z-[60] border-b border-white/[0.06] bg-[#0A0B12]">
        <div className="relative mx-auto flex min-h-[58px] max-w-[1480px] items-center justify-center px-4 sm:px-6 md:h-16 md:justify-start md:px-8">
          {/* Left: brand — OpenSplit wordmark, vertically centered, never cropped/stretched */}
          <img
            src="/brand/OpenSplit-navbar.svg"
            alt="OpenSplit"
            className="opensplit-wordmark h-8 w-[180px] shrink-0 object-contain object-center md:h-10 md:w-[240px] md:object-left"
          />

          {/* Desktop/tablet nav: centered as one group. */}
          <nav className="os-top-nav absolute inset-y-0 left-1/2 hidden -translate-x-1/2 items-stretch md:flex">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={navItemClass}>
                <item.icon className="h-4 w-4" strokeWidth={1.8} />
                {t(item.labelKey)}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Mobile nav: app-style bottom bar. */}
      <nav className="os-mobile-nav fixed inset-x-0 bottom-0 z-[70] border-t border-white/[0.08] bg-[#0A0B12]/95 px-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-2 shadow-[0_-18px_50px_rgba(0,0,0,0.32)] backdrop-blur-xl md:hidden">
        <div className="mx-auto flex max-w-md items-center gap-2 rounded-[1.35rem] border border-white/[0.08] bg-[#11131F] p-1.5">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={mobileNavItemClass}>
              <item.icon className="h-5 w-5" strokeWidth={1.9} />
              <span>{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  );
}
