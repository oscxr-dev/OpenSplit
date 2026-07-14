import { Globe2, ReceiptText, ShieldCheck } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { TopBar } from '@/components/layout/TopBar';
import { ErrorState } from '@/components/shared/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { usePublicTransparency } from '@/hooks/usePublicTransparency';
import { truncateMiddle } from '@/lib/transparency';
import type { PublicSplitMember, PublicSplitRule } from '@/types/api';

const orbitNodes = [
  { x: 50, y: 16 },
  { x: 78, y: 39 },
  { x: 63, y: 80 },
  { x: 22, y: 65 },
  { x: 23, y: 33 },
  { x: 50, y: 84 },
];

function publicLabel(member: PublicSplitMember, fallback: string) {
  if (member.label) return member.label;
  if (member.nostr_pubkey) return truncateMiddle(member.nostr_pubkey);
  return fallback;
}

function compactName(name: string) {
  const [first, last] = name.split(' ');
  return last ? `${first} ${last.charAt(0).replace('.', '')}.` : first;
}

function channelAngle(node: { x: number; y: number }) {
  const dx = node.x - 50;
  const dy = node.y - 50;
  return (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
}

function allocationRing(share: number, angle: number) {
  const degrees = Math.min(360, Math.max(0, share * 3.6));
  const connectionAngle = (angle + 180) % 360;
  const start = connectionAngle - degrees / 2;

  return `conic-gradient(from ${start}deg, rgba(255,46,147,0.92) 0deg ${degrees}deg, rgba(154,164,178,0.14) ${degrees}deg 360deg)`;
}

function nodeSize(share: number) {
  const size = Math.max(82, Math.min(116, 80 + share * 0.7));
  return `clamp(76px, ${(size / 6).toFixed(2)}vw, ${size}px)`;
}

function PublicRuleGraph({ rule, teamName }: { rule: PublicSplitRule; teamName: string }) {
  const { t } = useTranslation();
  const members = rule.distribution.filter((member) => member.percentage > 0);
  const total = members.reduce((sum, member) => sum + member.percentage, 0);
  const partnerFallback = t('public.transparency.publicPartner');

  return (
    <div
      className="relative min-h-[430px] overflow-hidden rounded-xl border border-[#2A2D3A] bg-[#11121A] p-4 shadow-[inset_0_1px_0_rgba(245,245,247,0.055),0_24px_70px_rgba(0,0,0,0.18)] sm:min-h-[500px] sm:p-6 lg:p-8"
      style={{
        background:
          'radial-gradient(circle at 50% 50%, rgba(255,46,147,0.12), rgba(82,34,64,0.11) 25%, rgba(24,26,38,0.86) 54%, rgba(17,18,26,0.98) 100%), linear-gradient(145deg, #181A26 0%, #12111B 54%, #11121A 100%)',
      }}
    >
      <div className="absolute left-4 top-4 z-30 rounded-full border border-[#FF2E93]/18 bg-[#151722]/88 px-3 py-1.5 text-xs font-semibold text-[#F5F5F7] backdrop-blur">
        {rule.name} <span className="font-mono text-[#9AA4B2]">v{rule.version}</span>
      </div>

      <div className="absolute right-4 top-4 z-30 rounded-full border border-[#2A2D3A] bg-[#151722]/88 px-3 py-1.5 font-mono text-xs font-semibold text-[#FF2E93] backdrop-blur">
        {t('public.transparency.publicPct', { total })}
      </div>

      <div className="absolute left-1/2 top-1/2 h-[78%] w-[78%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#9AA4B2]/[0.035] sm:h-[86%] sm:w-[86%]" />
      <div className="absolute left-1/2 top-1/2 h-[58%] w-[58%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#FF2E93]/[0.055] sm:h-[66%] sm:w-[66%]" />
      <div className="absolute left-1/2 top-1/2 h-[36%] w-[36%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#9AA4B2]/[0.045] sm:h-[42%] sm:w-[42%]" />

      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {members.map((member, index) => {
          const node = orbitNodes[index % orbitNodes.length];

          return (
            <line
              key={`${publicLabel(member, partnerFallback)}-${index}`}
              x1="50"
              y1="50"
              x2={node.x}
              y2={node.y}
              stroke="rgba(255,46,147,0.28)"
              strokeLinecap="round"
              strokeWidth={Math.max(0.65, Math.min(2.2, member.percentage / 24))}
            />
          );
        })}
      </svg>

      <div className="absolute left-1/2 top-1/2 z-20 flex h-32 w-32 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border border-[#FF2E93]/32 bg-[#151722] text-center shadow-[0_0_0_10px_rgba(255,46,147,0.045),0_0_58px_rgba(255,46,147,0.16)] sm:h-40 sm:w-40">
        <Globe2 className="h-6 w-6 text-[#FF2E93]" strokeWidth={1.8} />
        <p className="mt-3 px-4 text-sm font-semibold leading-5 text-[#F5F5F7]">{teamName}</p>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#9AA4B2]">{t('public.transparency.publicProofBadge')}</p>
      </div>

      {members.map((member, index) => {
        const node = orbitNodes[index % orbitNodes.length];
        const angle = channelAngle(node);
        const size = nodeSize(member.percentage);

        return (
          <div
            key={`${publicLabel(member, partnerFallback)}-${index}`}
            className="absolute z-30 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full p-[2px] text-center"
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
              width: size,
              height: size,
              background: allocationRing(member.percentage, angle),
              boxShadow: '0 16px 36px rgba(0,0,0,0.30)',
            }}
          >
            <span className="flex h-full w-full flex-col items-center justify-center rounded-full border border-[#9AA4B2]/[0.16] bg-[#171722] px-3">
              <span className="max-w-[86px] truncate text-xs font-semibold leading-tight text-[#F5F5F7] sm:text-sm">
                {compactName(publicLabel(member, partnerFallback))}
              </span>
              <span className="mt-1 font-mono text-[24px] font-semibold leading-none tracking-tight text-[#FF2E93] sm:text-[28px]">
                {member.percentage}%
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function PublicTransparencyPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const { data, isLoading, isError, refetch } = usePublicTransparency(slug);
  const publicRules = data?.public_rules ?? [];
  const publicPartnerCount = publicRules.reduce((sum, rule) => sum + rule.distribution.length, 0);
  const completedSplitCount = publicRules.reduce((sum, rule) => sum + rule.completed_split_count, 0);

  return (
    <div className="opensplit-app min-h-screen pt-20 text-[#F5F5F7] lg:pt-[68px]">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 pb-32 pt-6 sm:px-6 md:pb-6 lg:px-8">
        {isLoading && (
          <div className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
            <Skeleton className="h-[500px] w-full" />
          </div>
        )}

        {(!slug || isError) && (
          <ErrorState
            message={t('public.transparency.errorMessage')}
            onRetry={() => refetch()}
          />
        )}

        {data && (
          <>
            <section className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-[inset_0_1px_0_rgba(245,245,247,0.05)]">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#FF2E93]/22 bg-[#FF2E93]/10 text-[#FF2E93]">
                    <ReceiptText className="h-5 w-5" strokeWidth={1.8} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#FF2E93]">{t('public.transparency.summaryTitle')}</p>
                    <h1 className="mt-1 truncate text-xl font-semibold text-[#F5F5F7]">{data.name}</h1>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="font-mono text-lg font-semibold text-[#F5F5F7]">{publicRules.length}</p>
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.rules')}</p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="font-mono text-lg font-semibold text-[#F5F5F7]">{publicPartnerCount}</p>
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.partners')}</p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="font-mono text-lg font-semibold text-[#F5F5F7]">{completedSplitCount}</p>
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.splits')}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-[inset_0_1px_0_rgba(245,245,247,0.05)]">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#FF2E93]/22 bg-[#FF2E93]/10 text-[#FF2E93]">
                    <ShieldCheck className="h-5 w-5" strokeWidth={1.8} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#FF2E93]">{t('public.transparency.statusTitle')}</p>
                    <p className="mt-1 truncate text-xl font-semibold text-[#F5F5F7]">{t('public.transparency.privateHidden')}</p>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.walletData')}</p>
                    <p className="mt-1 text-sm font-semibold text-[#F5F5F7]">{t('public.transparency.notShown')}</p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.amounts')}</p>
                    <p className="mt-1 truncate font-mono text-sm font-semibold text-[#F5F5F7]">
                      {data.show_amounts && data.total_sats != null
                        ? `${data.total_sats.toLocaleString()} sats`
                        : t('public.transparency.hidden')}
                    </p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2">
                    <p className="text-[11px] text-[#94A3B8]">{t('public.transparency.recentActivity')}</p>
                    <p className="mt-1 font-mono text-sm font-semibold text-[#F5F5F7]">{data.recent_payments.length}</p>
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-4">
              {!publicRules.length ? (
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-8 text-center">
                  <ShieldCheck className="mx-auto h-8 w-8 text-[#FF2E93]" strokeWidth={1.8} />
                  <p className="mt-4 text-lg font-semibold text-[#F5F5F7]">
                    {t('public.transparency.noPublicRule')}
                  </p>
                </div>
              ) : (
                publicRules.map((rule, index) => (
                  <PublicRuleGraph key={`${rule.name}-${rule.version}-${index}`} rule={rule} teamName={data.name} />
                ))
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
