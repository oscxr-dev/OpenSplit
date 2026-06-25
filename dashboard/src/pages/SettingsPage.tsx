import { useState } from 'react';
import { Check, LogOut, Moon, ServerCog, ShieldCheck, Sun } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';

const themeOptions = [
  {
    value: 'dark' as const,
    label: 'Dark',
    description: 'Deep surfaces for the proof canvas.',
    icon: Moon,
  },
  {
    value: 'light' as const,
    label: 'Light',
    description: 'A brighter shell with strong contrast.',
    icon: Sun,
  },
];

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { logout, tenant } = useAuth();
  const navigate = useNavigate();
  const [publicPageOn, setPublicPageOn] = useState(false);
  const workspaceName = tenant?.tenant.brand_display_name || tenant?.tenant.name || 'OpenSplit';
  const publicSlug = tenant?.tenant.public_slug || slugify(tenant?.tenant.name || workspaceName);
  const connected = tenant?.lnbits_status === 'ok';

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-4xl font-semibold tracking-tight text-[#F5F5F7] sm:text-5xl">Workspace</h1>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="p-6 sm:p-8">
              <div className="flex items-center gap-3">
                <ServerCog className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                <h2 className="text-xl font-semibold text-[#F5F5F7]">BTCPay</h2>
              </div>
              <p className="mt-3 text-sm text-[#94A3B8]">{workspaceName}</p>
              <p className="mt-2 font-mono text-xs text-[#94A3B8]">{tenant?.tenant.id ?? 'workspace pending'}</p>
            </div>
            <div className="px-6 pb-6 sm:px-8 lg:p-8">
              <Badge variant={connected ? 'success' : 'error'}>{connected ? 'Connected' : 'Disconnected'}</Badge>
            </div>
          </div>

          <div className="border-t border-white/[0.07] p-6 sm:p-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <ShieldCheck className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                  <h2 className="font-semibold text-[#F5F5F7]">Public proof page</h2>
                </div>
                <p className="mt-3 text-sm leading-6 text-[#94A3B8]">
                  Shows the active split, recent public payments, and no private wallet data.
                </p>
                <p className="mt-2 font-mono text-xs text-[#94A3B8]">/public/{publicSlug}</p>
              </div>
              <button
                type="button"
                onClick={() => setPublicPageOn((value) => !value)}
                className={cn(
                  'inline-flex min-h-10 min-w-24 items-center justify-center rounded-full border px-5 text-sm font-semibold transition',
                  publicPageOn
                    ? 'public-toggle-on border-orange-300/50 bg-orange-500 text-white shadow-[0_0_0_4px_rgba(249,115,22,0.10)]'
                    : 'border-white/[0.16] bg-white text-[#11131F] hover:bg-white/90'
                )}
                aria-pressed={publicPageOn}
              >
                {publicPageOn ? 'On' : 'Off'}
              </button>
            </div>
          </div>

          <div className="border-t border-white/[0.07] p-6 sm:p-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold text-[#F5F5F7]">Appearance</h2>
                <p className="mt-2 text-sm leading-6 text-[#94A3B8]">
                  Switch between dark and light without making payment records harder to read.
                </p>
              </div>

              <div className="grid w-full max-w-xs grid-cols-2 gap-2 rounded-lg border border-white/[0.08] bg-white/[0.035] p-1.5">
                {themeOptions.map((option) => {
                  const selected = theme === option.value;

                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTheme(option.value)}
                      className={cn(
                        'relative inline-flex min-h-10 items-center justify-center gap-2 rounded-md text-sm font-semibold transition',
                        selected
                          ? 'bg-[#FF2D78] text-[#0A0B12]'
                          : 'text-[#94A3B8] hover:bg-white/[0.06] hover:text-[#F5F5F7]'
                      )}
                      title={option.description}
                    >
                      <option.icon className="h-4 w-4" strokeWidth={1.8} />
                      {option.label}
                      {selected && <Check className="absolute right-2 h-3.5 w-3.5" strokeWidth={2} />}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Button
        variant="ghost"
        onClick={() => {
          logout();
          navigate('/login');
        }}
      >
        <LogOut className="h-4 w-4" strokeWidth={1.8} />
        Sign out
      </Button>
    </div>
  );
}
